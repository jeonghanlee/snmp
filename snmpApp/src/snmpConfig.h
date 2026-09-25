#ifndef SNMP_CONFIG_H
#define SNMP_CONFIG_H

#include <string>
#include <vector>

/* Validated startup configuration for named SNMPv3 profiles and endpoints.
 *
 * Profiles and endpoints are defined by IOC shell commands before records
 * load and are never deleted or redefined. Every entry is validated
 * completely before it is published; a failed definition leaves no trace. A
 * record binding freezes its endpoint, and iocInit freezes every definition.
 * The registry lives for the process, so references it returns stay valid.
 * All calls come from the IOC shell or record initialization thread.
 *
 * Diagnostics name the file role, line number and field, never a value or
 * a source line. Passphrases are cleared from owned storage when released. */

enum SnmpSecurityLevel { SnmpNoAuthNoPriv = 1, SnmpAuthNoPriv = 2, SnmpAuthPriv = 3 };

/* Immutable USM profile. authProtocol and privProtocol hold the library's
 * protocol OIDs; they are empty when the level does not use them. */
struct SnmpProfileConfig {
    std::string name;
    std::string securityName;
    std::string contextName;
    SnmpSecurityLevel securityLevel;
    std::string authType;
    std::string privType;
    std::vector<unsigned long> authProtocol;
    std::vector<unsigned long> privProtocol;
    std::string authPassphrase;
    std::string privPassphrase;
    unsigned long long revision;

    SnmpProfileConfig();
    ~SnmpProfileConfig();
};

/* Named endpoint. A negative timeoutMSec, retries or maxOidsPerReq inherits
 * the transport default. Empty engine IDs select automatic discovery and the
 * default context engine. invalid records that a setting call for this
 * endpoint was rejected; such an endpoint refuses record binding. */
struct SnmpEndpointConfig {
    std::string name;
    std::string address;
    const SnmpProfileConfig *profile;
    int timeoutMSec;
    int retries;
    int maxOidsPerReq;
    std::vector<unsigned char> securityEngineID;
    std::vector<unsigned char> contextEngineID;
    bool bound;
    bool invalid;
};

bool snmpConfigLoadProfile(const char *name, const char *filename, std::string &error);
bool snmpConfigDefineEndpoint(const char *name, const char *address, const char *profile, std::string &error);
bool snmpConfigSetEndpointParam(const char *name, const char *parameter, const char *value, std::string &error);

/* Binds a record to a defined endpoint and freezes that endpoint. Returns
 * NULL with error set for an unknown name or an endpoint with a rejected
 * setting. Binding happens during record initialization, before iocInit
 * freezes the registry. */
const SnmpEndpointConfig *snmpConfigBindEndpoint(const char *name, std::string &error);

/* Freezes every definition; later definition calls fail. */
void snmpConfigFreeze();
bool snmpConfigFrozen();

/* Parses an SnmpEngineID: contiguous hex byte pairs with an optional 0x or
 * 0X prefix, 5 through 32 bytes, neither all zero nor all 0xFF. */
bool snmpConfigParseEngineID(const char *text, std::vector<unsigned char> &bytes, std::string &error);

/* Clears a secret string's bytes with a store the compiler keeps. */
void snmpConfigClear(std::string &secret);

#endif
