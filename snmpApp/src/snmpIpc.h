#ifndef SNMP_IPC_H
#define SNMP_IPC_H

#include "snmpTypes.h"
#include <stddef.h>
#include <stdint.h>
#include <string>
#include <vector>

namespace snmpIpc {

const size_t headerBytes = 32;
const size_t maxFrameBytes = 256 * 1024;
const unsigned startupMSec = 5000;
enum Kind { Bootstrap = 1, Ready, Bind, Bound, Transaction, Result, Stop };

/* Private protocol values are encoded explicitly, never as native structs.
 * A decoder checks the length before copying or allocating any field. */
class Writer {
public:
    std::vector<unsigned char> bytes;
    void u32(uint32_t value);
    void u64(uint64_t value);
    void blob(const void *data, size_t length);
    void string(const std::string &value);
    void value(const SnmpValue &value);
};

class Reader {
public:
    explicit Reader(const std::vector<unsigned char> &bytes);
    uint32_t u32();
    uint64_t u64();
    std::vector<unsigned char> blob(size_t maximum);
    std::string string(size_t maximum);
    bool value(SnmpValue &value, bool payload = false);
    bool done() const;
    bool good() const { return valid; }
private:
    const std::vector<unsigned char> &bytes;
    size_t position;
    bool valid;
};

struct Frame {
    Kind kind;
    uint64_t epoch, transaction;
    std::vector<unsigned char> payload;
};

std::vector<unsigned char> encode(const Frame &frame);

/* One nonblocking stream; receive() returns 1 for a complete frame, 0 for
 * incomplete input, -1 for EOF or an invalid frame. It reads only the exact
 * header/payload remaining, so input storage never exceeds one frame. */
class Channel {
public:
    explicit Channel(int descriptor = -1);
    int fd;
    std::vector<unsigned char> output;
    bool queue(const Frame &frame);
    bool flush();
    int receive(Frame &frame);
    bool writing() const { return sent < output.size(); }
    void reset(int descriptor);
private:
    std::vector<unsigned char> input;
    size_t sent, expected;
};

uint64_t now();
bool deadline(uint64_t intervalMSec, uint64_t &absolute);
bool watchdog(long timeoutUs, int retries, uint64_t &requiredMSec);
void clear(std::vector<unsigned char> &bytes);

}
#endif
