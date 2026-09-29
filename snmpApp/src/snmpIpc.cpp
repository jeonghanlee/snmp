#include "snmpIpc.h"
#include <algorithm>
#include <cmath>
#include <errno.h>
#include <limits.h>
#include <stdexcept>
#include <string.h>
#include <sys/socket.h>
#include <time.h>

namespace snmpIpc {
namespace {
const uint32_t magic = 0x534e4d50;
const uint32_t version = 1;
const uint64_t nanosecondsPerMSec = 1000000;
uint64_t ceiling(uint64_t n, uint64_t d) { return n / d + (n % d != 0); }
void reserveField(size_t present, size_t extra)
{
    if (extra > maxFrameBytes - headerBytes || present > maxFrameBytes - headerBytes - extra)
        throw std::length_error("worker frame exceeds limit");
}
}

void clear(std::vector<unsigned char> &bytes)
{
    volatile unsigned char *p = bytes.empty() ? NULL : &bytes[0];
    for (size_t i = 0; i < bytes.size(); ++i) p[i] = 0;
    bytes.clear();
}

void Writer::u32(uint32_t v)
{
    reserveField(bytes.size(), 4);
    for (int s = 24; s >= 0; s -= 8) bytes.push_back((v >> s) & 255);
}
void Writer::u64(uint64_t v) { u32(v >> 32); u32(v & UINT32_MAX); }
void Writer::blob(const void *p, size_t n)
{
    if (n > maxFrameBytes - headerBytes - 4) throw std::length_error("worker field exceeds limit");
    reserveField(bytes.size(), n + 4);
    u32(n);
    if (n) bytes.insert(bytes.end(), (const unsigned char *)p, (const unsigned char *)p + n);
}
void Writer::string(const std::string &v) { blob(v.data(), v.size()); }
void Writer::value(const SnmpValue &v)
{
    u32(v.kind); u32(v.wireType); u32(v.valid); u32(v.hasLong); u32(v.hasDouble);
    u64(static_cast<uint64_t>(v.signedValue)); u64(v.unsignedValue);
    uint64_t bits;
    static_assert(sizeof(bits) == sizeof(v.realValue), "IPC requires binary64 storage");
    memcpy(&bits, &v.realValue, sizeof(bits));
    u64(bits);
    size_t textLength = v.text.empty() ? 0 : strnlen(&v.text[0], v.text.size());
    if (textLength == v.text.size() || v.length > v.bytes.size())
        throw std::length_error("invalid worker value storage");
    blob(v.text.empty() ? NULL : &v.text[0], textLength);
    blob(v.length ? &v.bytes[0] : NULL, v.length);
    u32(v.oid.size());
    for (size_t i = 0; i < v.oid.size(); ++i) u32(v.oid[i]);
}

Reader::Reader(const std::vector<unsigned char> &v) : bytes(v), position(0), valid(true) {}
uint32_t Reader::u32()
{
    if (!valid || bytes.size() - position < 4) { valid = false; return 0; }
    uint32_t v = 0;
    for (unsigned i = 0; i < 4; ++i) v = (v << 8) | bytes[position++];
    return v;
}
uint64_t Reader::u64() { uint64_t high = u32(); return (high << 32) | u32(); }
std::vector<unsigned char> Reader::blob(size_t maximum)
{
    size_t n = u32();
    if (!valid || n > maximum || n > bytes.size() - position) { valid = false; return {}; }
    std::vector<unsigned char> v(bytes.begin() + position, bytes.begin() + position + n);
    position += n;
    return v;
}
std::string Reader::string(size_t maximum)
{
    std::vector<unsigned char> v = blob(maximum);
    std::string s(v.begin(), v.end());
    clear(v);
    if (s.find('\0') != std::string::npos) valid = false;
    return s;
}
bool Reader::done() const { return valid && position == bytes.size(); }
bool Reader::value(SnmpValue &v, bool payload, bool legacy)
{
    unsigned kind = u32(), wire = u32(), success = u32(), asLong = u32(), asDouble = u32();
    uint64_t signedBits = u64();
    v.signedValue = signedBits <= INT64_MAX ? static_cast<int64_t>(signedBits)
                                          : -1 - static_cast<int64_t>(UINT64_MAX - signedBits);
    v.unsignedValue = u64();
    uint64_t bits = u64();
    memcpy(&v.realValue, &bits, sizeof(bits));
    std::string text = string(v.text.empty() ? 0 : v.text.size() - 1);
    std::vector<unsigned char> data = blob(v.bytes.size());
    unsigned count = u32();
    if (kind > SnmpValue::ObjectId || wire > 255 || success > 1 || asLong > 1 || asDouble > 1 ||
        count > 128 || !std::isfinite(v.realValue)) valid = false;
    if (success && !payload) {
        unsigned expectedKind = SnmpValue::Empty;
        bool expectedLong = false, expectedDouble = false;
        switch (wire) {
        case 2: expectedKind = SnmpValue::Signed; expectedLong = true; break;
        case 0x41: case 0x42: expectedKind = SnmpValue::Unsigned; expectedLong = true; break;
        case 0x43: case 0x46: expectedKind = SnmpValue::Unsigned; break;
        case 0x78: case 0x79: expectedKind = SnmpValue::Real; expectedDouble = true; break;
        case 6: expectedKind = SnmpValue::ObjectId; break;
        case 3: case 4: case 0x40: case 0x44: expectedKind = SnmpValue::Octets; break;
        case 0x80: case 0x81: case 0x82: if (!legacy) valid = false; break;
        default: valid = false;
        }
        if (kind != expectedKind || asLong != expectedLong || asDouble != expectedDouble ||
            (kind != SnmpValue::Octets && !data.empty()) || (kind != SnmpValue::ObjectId && count)) valid = false;
    }
    v.oid.clear();
    if (!valid) return false;
    for (unsigned i = 0; i < count; ++i) v.oid.push_back(u32());
    if (!valid || v.text.empty()) return false;
    v.kind = static_cast<SnmpValue::Kind>(kind);
    v.wireType = wire; v.valid = success; v.hasLong = asLong; v.hasDouble = asDouble;
    memcpy(&v.text[0], text.c_str(), text.size() + 1);
    v.length = data.size();
    std::copy(data.begin(), data.end(), v.bytes.begin());
    return true;
}

std::vector<unsigned char> encode(const Frame &f)
{
    if (f.kind < Bootstrap || f.kind > Stop || f.payload.size() > maxFrameBytes - headerBytes)
        throw std::length_error("invalid worker frame");
    Writer w;
    w.u32(magic); w.u32((version << 16) | f.kind); w.u32(f.payload.size()); w.u32(0);
    w.u64(f.epoch); w.u64(f.transaction);
    w.bytes.insert(w.bytes.end(), f.payload.begin(), f.payload.end());
    return w.bytes;
}
Channel::Channel(int descriptor) : fd(descriptor), sent(0), expected(headerBytes) {}
void Channel::reset(int descriptor)
{
    clear(input); clear(output); sent = 0; expected = headerBytes; fd = descriptor;
}
bool Channel::queue(const Frame &f)
{
    if (writing()) return false;
    clear(output);
    output = encode(f); sent = 0;
    return true;
}
bool Channel::flush()
{
    if (!writing()) return true;
    ssize_t n = send(fd, &output[sent], output.size() - sent, MSG_NOSIGNAL | MSG_DONTWAIT);
    if (n > 0) sent += static_cast<size_t>(n);
    else if (n == 0 || (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)) return false;
    if (!writing()) { clear(output); sent = 0; }
    return true;
}
int Channel::receive(Frame &f)
{
    unsigned char buffer[8192];
    ssize_t n = recv(fd, buffer, std::min(sizeof(buffer), expected - input.size()), MSG_DONTWAIT);
    if (n == 0) return -1;
    if (n < 0) return errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK ? 0 : -1;
    input.insert(input.end(), buffer, buffer + n);
    if (input.size() < expected) return 0;
    Reader r(input);
    uint32_t gotMagic = r.u32(), tag = r.u32(), length = r.u32(), reserved = r.u32();
    uint64_t epoch = r.u64(), transaction = r.u64();
    if (gotMagic != magic || (tag >> 16) != version || (tag & 65535) < Bootstrap ||
        (tag & 65535) > Stop || reserved || length > maxFrameBytes - headerBytes || !epoch) return -1;
    expected = headerBytes + length;
    if (input.size() < expected) return 0;
    f.kind = static_cast<Kind>(tag & 65535); f.epoch = epoch; f.transaction = transaction;
    f.payload.assign(input.begin() + headerBytes, input.end());
    clear(input); expected = headerBytes;
    return 1;
}

uint64_t now()
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) throw std::runtime_error("monotonic clock unavailable");
    return static_cast<uint64_t>(t.tv_sec) * 1000000000 + t.tv_nsec;
}
bool deadline(uint64_t ms, uint64_t &absolute)
{
    uint64_t start = now();
    if (!ms || ms > (UINT64_MAX - start) / nanosecondsPerMSec) return false;
    absolute = start + ms * nanosecondsPerMSec;
    return true;
}
bool watchdog(long timeoutUs, int retries, uint64_t &requiredMSec)
{
    if (timeoutUs <= 0 || retries < 0 || retries > INT_MAX - 1) return false;
    uint64_t t = timeoutUs, intervals = static_cast<uint64_t>(retries) * 2 + 3;
    if (t > UINT64_MAX / intervals) return false;
    uint64_t budget = intervals * t;
    uint64_t allowance = std::max(UINT64_C(5000000), std::max(t * 2, ceiling(budget, 10)));
    if (budget > UINT64_MAX - allowance) return false;
    requiredMSec = ceiling(budget + allowance, 1000);
    return requiredMSec <= UINT64_MAX / nanosecondsPerMSec;
}
}
