#include "snmpConfig.h"
#include "snmpNative.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <map>
#include <memory>

namespace {

const size_t maxFileBytes = 16384;
const size_t maxLineBytes = 4096;
const size_t minPassphrase = 8;
const size_t maxPassphrase = 1024;
const size_t maxSecurityName = 32;
const size_t maxContextName = 32;
const size_t maxNameLength = 63;
const size_t maxAddressLength = 255;
const size_t minEngineID = 5;
const size_t maxEngineID = 32;
const unsigned keyBufferBytes = 64;

/* Algorithm spellings a named profile may select. The linked library still
 * resolves each one; site policy only narrows its accepted names. */
const char *const permittedAuth[] = {"SHA", "SHA-224", "SHA-256", "SHA-384", "SHA-512", NULL};
const char *const permittedPriv[] = {"AES128", NULL};

struct Line {
    unsigned number;
    std::string key;
    std::string value;
};

bool frozen = false;
unsigned long long nextRevision = 0;
std::map<std::string, std::unique_ptr<SnmpProfileConfig> > profiles;
std::map<std::string, std::unique_ptr<SnmpEndpointConfig> > endpoints;

bool validName(const char *name)
{
    if (!name || !isalpha((unsigned char)name[0])) return false;
    size_t length = strlen(name);
    if (length > maxNameLength) return false;
    for (size_t i = 1; i < length; ++i) {
        unsigned char c = name[i];
        if (!isalnum(c) && c != '_' && c != '.' && c != '-') return false;
    }
    return true;
}

bool permitted(const char *const *list, const std::string &value)
{
    for (; *list; ++list)
        if (value == *list) return true;
    return false;
}

std::string lineError(const char *role, unsigned line, const char *text)
{
    char buffer[160];
    snprintf(buffer, sizeof(buffer), "%s file line %u: %s", role, line, text);
    return buffer;
}

/* Reads a complete configuration file. The file is opened without blocking,
 * so a FIFO or device is rejected by the regular-file check instead of
 * stalling startup. A credential file is opened without following its final
 * symlink and must be owned by root or the effective user with no group or
 * other permission bits. Every line, including the last, must end with a
 * newline; an unterminated last line is treated as truncated. */
bool readFile(const char *role, const char *path, bool credential, std::vector<Line> &lines, std::string &error)
{
    if (!path || path[0] != '/') {
        error = std::string(role) + " file path must be absolute";
        return false;
    }
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NONBLOCK | (credential ? O_NOFOLLOW : 0));
    if (fd < 0) {
        error = std::string(role) + (errno == ELOOP ? " file is a symbolic link" : " file cannot be opened");
        return false;
    }
    struct stat status;
    std::string content;
    bool ok = !fstat(fd, &status);
    if (ok && !S_ISREG(status.st_mode)) {
        error = std::string(role) + " file is not a regular file";
        ok = false;
    }
    if (ok && fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) & ~O_NONBLOCK) < 0) {
        error = std::string(role) + " file cannot be read";
        ok = false;
    }
    if (ok && credential && status.st_uid != 0 && status.st_uid != geteuid()) {
        error = std::string(role) + " file owner must be root or the IOC user";
        ok = false;
    }
    if (ok && credential && (status.st_mode & (S_IRWXG | S_IRWXO))) {
        error = std::string(role) + " file must not grant group or other permissions";
        ok = false;
    }
    if (ok) {
        char buffer[1024];
        ssize_t count;
        while ((count = read(fd, buffer, sizeof(buffer))) > 0) {
            content.append(buffer, (size_t)count);
            if (content.size() > maxFileBytes) break;
        }
        memset(buffer, 0, sizeof(buffer));
        if (count < 0) {
            error = std::string(role) + " file cannot be read";
            ok = false;
        } else if (content.size() > maxFileBytes) {
            error = std::string(role) + " file exceeds 16 KiB";
            ok = false;
        } else if (content.find('\0') != std::string::npos) {
            error = std::string(role) + " file contains a NUL byte";
            ok = false;
        } else if (!content.empty() && content[content.size() - 1] != '\n') {
            unsigned lines = 1;
            for (size_t i = 0; i < content.size(); ++i)
                if (content[i] == '\n') ++lines;
            error = lineError(role, lines, "line is not terminated by a newline");
            ok = false;
        }
    }
    close(fd);
    unsigned number = 0;
    size_t start = 0;
    while (ok && start < content.size()) {
        size_t end = content.find('\n', start);
        if (end == std::string::npos) end = content.size();
        ++number;
        if (end - start > maxLineBytes) {
            error = lineError(role, number, "line exceeds 4096 bytes");
            ok = false;
            break;
        }
        size_t first = start;
        while (first < end && isspace((unsigned char)content[first])) ++first;
        if (first < end && content[first] != '#') {
            size_t keyEnd = first;
            while (keyEnd < end && !isspace((unsigned char)content[keyEnd])) ++keyEnd;
            size_t valueStart = keyEnd;
            while (valueStart < end && isspace((unsigned char)content[valueStart])) ++valueStart;
            size_t valueEnd = end;
            while (valueEnd > valueStart && isspace((unsigned char)content[valueEnd - 1])) --valueEnd;
            if (valueStart >= valueEnd) {
                error = lineError(role, number, "missing value");
                ok = false;
                break;
            }
            Line line;
            line.number = number;
            line.key.assign(content, first, keyEnd - first);
            line.value.assign(content, valueStart, valueEnd - valueStart);
            lines.push_back(line);
        }
        start = end + 1;
    }
    snmpConfigClear(content);
    if (!ok) {
        for (size_t i = 0; i < lines.size(); ++i) snmpConfigClear(lines[i].value);
        lines.clear();
    }
    return ok;
}

void clearLines(std::vector<Line> &lines)
{
    for (size_t i = 0; i < lines.size(); ++i) snmpConfigClear(lines[i].value);
    lines.clear();
}

/* Assigns known keys once each; an unknown or repeated key is an error. */
bool assign(const char *role, std::vector<Line> &lines, const char *const *keys,
            std::map<std::string, std::string> &values, std::string &error)
{
    for (size_t i = 0; i < lines.size(); ++i) {
        const Line &line = lines[i];
        bool known = false;
        for (const char *const *key = keys; *key; ++key)
            if (line.key == *key) known = true;
        if (!known) {
            error = lineError(role, line.number, "unknown field");
            return false;
        }
        if (values.count(line.key)) {
            error = lineError(role, line.number, ("duplicate field " + line.key).c_str());
            return false;
        }
        values[line.key] = line.value;
    }
    return true;
}

void clearValues(std::map<std::string, std::string> &values)
{
    for (std::map<std::string, std::string>::iterator i = values.begin(); i != values.end(); ++i)
        snmpConfigClear(i->second);
    values.clear();
}

bool parseProfile(const char *filename, SnmpProfileConfig &profile, std::string &credentialFile, std::string &error)
{
    static const char *const keys[] = {"securityName", "securityLevel", "authType", "privType", "contextName",
                                       "credentialFile", NULL};
    std::vector<Line> lines;
    std::map<std::string, std::string> values;
    if (!readFile("profile", filename, false, lines, error)) return false;
    bool ok = assign("profile", lines, keys, values, error);
    clearLines(lines);
    if (!ok) return false;
    if (!values.count("securityName") || !values.count("securityLevel")) {
        error = "profile requires securityName and securityLevel";
        return false;
    }
    profile.securityName = values["securityName"];
    if (profile.securityName.size() > maxSecurityName) {
        error = "profile securityName exceeds 32 bytes";
        return false;
    }
    const std::string &level = values["securityLevel"];
    if (level == "noAuthNoPriv") profile.securityLevel = SnmpNoAuthNoPriv;
    else if (level == "authNoPriv") profile.securityLevel = SnmpAuthNoPriv;
    else if (level == "authPriv") profile.securityLevel = SnmpAuthPriv;
    else {
        error = "profile securityLevel is not noAuthNoPriv, authNoPriv or authPriv";
        return false;
    }
    bool authenticated = profile.securityLevel != SnmpNoAuthNoPriv;
    bool privacy = profile.securityLevel == SnmpAuthPriv;
    if (authenticated != (values.count("authType") != 0)) {
        error = authenticated ? "profile requires authType for this securityLevel"
                              : "profile authType is not used by noAuthNoPriv";
        return false;
    }
    if (privacy != (values.count("privType") != 0)) {
        error = privacy ? "profile requires privType for authPriv" : "profile privType is used only by authPriv";
        return false;
    }
    if (authenticated != (values.count("credentialFile") != 0)) {
        error = authenticated ? "profile requires credentialFile for this securityLevel"
                              : "profile credentialFile is not used by noAuthNoPriv";
        return false;
    }
    if (values.count("contextName")) {
        profile.contextName = values["contextName"];
        if (profile.contextName.size() > maxContextName) {
            error = "profile contextName exceeds 32 bytes";
            return false;
        }
    }
    if (authenticated) {
        profile.authType = values["authType"];
        if (!permitted(permittedAuth, profile.authType)) {
            error = "profile authType is not permitted by policy";
            return false;
        }
        if (!snmpNativeAuthProtocol(profile.authType.c_str(), profile.authProtocol)) {
            error = "profile authType is unavailable in the linked library";
            return false;
        }
        credentialFile = values["credentialFile"];
    }
    if (privacy) {
        profile.privType = values["privType"];
        if (!permitted(permittedPriv, profile.privType)) {
            error = "profile privType is not permitted by policy";
            return false;
        }
        if (!snmpNativePrivProtocol(profile.privType.c_str(), profile.privProtocol)) {
            error = "profile privType is unavailable in the linked library";
            return false;
        }
    }
    return true;
}

bool derivable(const SnmpProfileConfig &profile, const std::string &passphrase)
{
    unsigned char key[keyBufferBytes];
    size_t length = sizeof(key);
    bool ok = snmpNativeDeriveKey(&profile.authProtocol[0], profile.authProtocol.size(), passphrase, key, &length);
    memset(key, 0, sizeof(key));
    return ok;
}

bool parseCredentials(const std::string &filename, SnmpProfileConfig &profile, std::string &error)
{
    static const char *const keys[] = {"authPassPhrase", "privPassPhrase", NULL};
    std::vector<Line> lines;
    std::map<std::string, std::string> values;
    if (!readFile("credential", filename.c_str(), true, lines, error)) return false;
    bool ok = assign("credential", lines, keys, values, error);
    clearLines(lines);
    bool privacy = profile.securityLevel == SnmpAuthPriv;
    if (ok && !values.count("authPassPhrase")) {
        error = "credential file requires authPassPhrase";
        ok = false;
    }
    if (ok && privacy != (values.count("privPassPhrase") != 0)) {
        error = privacy ? "credential file requires privPassPhrase for authPriv"
                        : "credential privPassPhrase is used only by authPriv";
        ok = false;
    }
    for (std::map<std::string, std::string>::iterator i = values.begin(); ok && i != values.end(); ++i) {
        if (i->second.size() < minPassphrase || i->second.size() > maxPassphrase) {
            error = "credential " + i->first + " must be 8 through 1024 bytes";
            ok = false;
        }
    }
    if (ok) {
        profile.authPassphrase = values["authPassPhrase"];
        if (privacy) profile.privPassphrase = values["privPassPhrase"];
        if (!derivable(profile, profile.authPassphrase) ||
            (privacy && !derivable(profile, profile.privPassphrase))) {
            error = "credential key derivation failed";
            ok = false;
        }
    }
    clearValues(values);
    return ok;
}

bool parseDecimal(const char *text, long low, long high, long &value)
{
    if (!text || !*text || strlen(text) > 9) return false;
    long result = 0;
    for (const char *c = text; *c; ++c) {
        if (!isdigit((unsigned char)*c)) return false;
        result = result * 10 + (*c - '0');
    }
    if (result < low || result > high) return false;
    value = result;
    return true;
}

/* Rejects a second profile for the same securityName at the same address
 * whose protocols or credential bytes differ; one address will share one
 * worker and its USM user state. */
bool compatible(const SnmpEndpointConfig &candidate, std::string &error)
{
    const SnmpProfileConfig &a = *candidate.profile;
    for (std::map<std::string, std::unique_ptr<SnmpEndpointConfig> >::const_iterator i = endpoints.begin();
         i != endpoints.end(); ++i) {
        const SnmpEndpointConfig &other = *i->second;
        const SnmpProfileConfig &b = *other.profile;
        if (other.address != candidate.address || b.securityName != a.securityName) continue;
        if (a.authProtocol != b.authProtocol || a.privProtocol != b.privProtocol ||
            a.authPassphrase != b.authPassphrase || a.privPassphrase != b.privPassphrase) {
            error = "endpoint profile conflicts with endpoint " + other.name +
                    ": same address and securityName with different protocols or credentials";
            return false;
        }
    }
    return true;
}

}

SnmpProfileConfig::SnmpProfileConfig() : securityLevel(SnmpNoAuthNoPriv), revision(0)
{
}

SnmpProfileConfig::~SnmpProfileConfig()
{
    snmpConfigClear(authPassphrase);
    snmpConfigClear(privPassphrase);
}

void snmpConfigClear(std::string &secret)
{
    if (!secret.empty()) explicit_bzero(&secret[0], secret.size());
    secret.clear();
}

bool snmpConfigLoadProfile(const char *name, const char *filename, std::string &error)
{
    if (frozen) {
        error = "configuration is frozen after iocInit";
        return false;
    }
    if (!validName(name)) {
        error = "invalid profile name";
        return false;
    }
    if (profiles.count(name)) {
        error = std::string("duplicate profile ") + name;
        return false;
    }
    std::unique_ptr<SnmpProfileConfig> profile(new SnmpProfileConfig);
    profile->name = name;
    std::string credentialFile;
    if (!parseProfile(filename, *profile, credentialFile, error)) {
        error = std::string("profile ") + name + ": " + error;
        return false;
    }
    if (profile->securityLevel != SnmpNoAuthNoPriv && !parseCredentials(credentialFile, *profile, error)) {
        error = std::string("profile ") + name + ": " + error;
        return false;
    }
    profile->revision = ++nextRevision;
    profiles[name] = std::move(profile);
    return true;
}

bool snmpConfigDefineEndpoint(const char *name, const char *address, const char *profile, std::string &error)
{
    if (frozen) {
        error = "configuration is frozen after iocInit";
        return false;
    }
    if (!validName(name)) {
        error = "invalid endpoint name";
        return false;
    }
    if (endpoints.count(name)) {
        error = std::string("duplicate endpoint ") + name;
        return false;
    }
    size_t length = address ? strlen(address) : 0;
    if (!length || length > maxAddressLength) {
        error = std::string("endpoint ") + name + ": invalid address";
        return false;
    }
    for (size_t i = 0; i < length; ++i) {
        if (isspace((unsigned char)address[i])) {
            error = std::string("endpoint ") + name + ": invalid address";
            return false;
        }
    }
    std::map<std::string, std::unique_ptr<SnmpProfileConfig> >::const_iterator found =
        profile ? profiles.find(profile) : profiles.end();
    if (found == profiles.end()) {
        error = std::string("endpoint ") + name + ": unknown profile";
        return false;
    }
    std::unique_ptr<SnmpEndpointConfig> endpoint(new SnmpEndpointConfig);
    endpoint->name = name;
    endpoint->address = address;
    endpoint->profile = found->second.get();
    endpoint->timeoutMSec = endpoint->retries = endpoint->maxOidsPerReq = -1;
    endpoint->bound = false;
    endpoint->invalid = false;
    if (!compatible(*endpoint, error)) {
        error = std::string("endpoint ") + name + ": " + error;
        return false;
    }
    endpoints[name] = std::move(endpoint);
    return true;
}

bool snmpConfigSetEndpointParam(const char *name, const char *parameter, const char *value, std::string &error)
{
    if (frozen) {
        error = "configuration is frozen after iocInit";
        return false;
    }
    std::map<std::string, std::unique_ptr<SnmpEndpointConfig> >::iterator found =
        name ? endpoints.find(name) : endpoints.end();
    if (found == endpoints.end()) {
        error = "unknown endpoint";
        return false;
    }
    SnmpEndpointConfig &endpoint = *found->second;
    std::string prefix = "endpoint " + endpoint.name + ": ";
    bool invalid = endpoint.invalid;
    // Any rejected setting leaves the endpoint's startup configuration
    // incomplete, so records bound to it fail instead of running with defaults.
    endpoint.invalid = true;
    if (endpoint.bound) {
        error = prefix + "endpoint is bound by a record";
        return false;
    }
    std::string field = parameter ? parameter : "";
    long number = 0;
    if (field == "timeoutMSec") {
        if (!parseDecimal(value, 1, 60000, number)) {
            error = prefix + "timeoutMSec must be 1 through 60000";
            return false;
        }
        endpoint.timeoutMSec = (int)number;
    } else if (field == "retries") {
        if (!parseDecimal(value, 0, 5, number)) {
            error = prefix + "retries must be 0 through 5";
            return false;
        }
        endpoint.retries = (int)number;
    } else if (field == "maxOidsPerReq") {
        if (!parseDecimal(value, 1, 1024, number)) {
            error = prefix + "maxOidsPerReq must be 1 through 1024";
            return false;
        }
        endpoint.maxOidsPerReq = (int)number;
    } else if (field == "securityEngineID" || field == "contextEngineID") {
        std::vector<unsigned char> bytes;
        if (!snmpConfigParseEngineID(value, bytes, error)) {
            error = prefix + field + " " + error;
            return false;
        }
        (field == "securityEngineID" ? endpoint.securityEngineID : endpoint.contextEngineID) = bytes;
    } else {
        error = prefix + "unknown parameter";
        return false;
    }
    endpoint.invalid = invalid;
    return true;
}

const SnmpEndpointConfig *snmpConfigBindEndpoint(const char *name, std::string &error)
{
    std::map<std::string, std::unique_ptr<SnmpEndpointConfig> >::iterator found =
        name ? endpoints.find(name) : endpoints.end();
    if (found == endpoints.end()) {
        error = "unknown named endpoint";
        return NULL;
    }
    if (found->second->invalid) {
        error = "named endpoint has invalid startup configuration";
        return NULL;
    }
    found->second->bound = true;
    return found->second.get();
}

void snmpConfigFreeze()
{
    frozen = true;
}

bool snmpConfigFrozen()
{
    return frozen;
}

bool snmpConfigParseEngineID(const char *text, std::vector<unsigned char> &bytes, std::string &error)
{
    if (!text || !*text) {
        error = "is empty";
        return false;
    }
    if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) text += 2;
    size_t digits = strlen(text);
    if (!digits || digits % 2) {
        error = "needs an even number of hex digits";
        return false;
    }
    std::vector<unsigned char> parsed;
    for (size_t i = 0; i < digits; i += 2) {
        if (!isxdigit((unsigned char)text[i]) || !isxdigit((unsigned char)text[i + 1])) {
            error = "contains a non-hex character";
            return false;
        }
        char pair[3] = {text[i], text[i + 1], 0};
        parsed.push_back((unsigned char)strtoul(pair, NULL, 16));
    }
    if (parsed.size() < minEngineID || parsed.size() > maxEngineID) {
        error = "must be 5 through 32 bytes";
        return false;
    }
    bool zero = true, ones = true;
    for (size_t i = 0; i < parsed.size(); ++i) {
        zero = zero && parsed[i] == 0;
        ones = ones && parsed[i] == 0xFF;
    }
    if (zero || ones) {
        error = "must not be all zero or all 0xFF";
        return false;
    }
    bytes = parsed;
    return true;
}
