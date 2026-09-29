#ifndef SNMP_TYPES_H
#define SNMP_TYPES_H

#include <stdint.h>
#include <string>
#include <vector>

typedef unsigned long long SnmpIdentity;

enum SnmpOperation { SnmpGet, SnmpSet };

/* SNMP type a request output sends and expects back; the transport maps it
 * to the library's ASN constant so the adapter stays free of Net-SNMP. */
enum SnmpWireType { SnmpWireNone = 0, SnmpWireInteger, SnmpWireFloat, SnmpWireOctets };

/* Immutable per-record binding fixed at record initialization. id repeats the
 * completion handle; profile is the host/community group creation ordinal
 * held for the later validated-profile component; operation is SnmpGet for a
 * request input and SnmpSet for a request output. wireType is the SNMP type
 * a request output sends and expects back; it is SnmpWireNone for inputs. */
struct SnmpBinding {
    SnmpIdentity id;
    SnmpIdentity profile;
    SnmpOperation operation;
    SnmpWireType wireType;
    std::string name;
    std::vector<unsigned long> oid;
    unsigned capacity;
};

/* The acquisition service knows only an immutable handle and admission call.
 * The destination owns record pointers and the callback storage. */
struct SnmpCompletion {
    SnmpIdentity handle;
    bool (*schedule)(SnmpIdentity handle);
};

/* Storage is reserved during binding. Native response buffers never escape
 * the transport boundary. Text is a bounded legacy conversion view. */
struct SnmpValue {
    enum Kind { Empty, Signed, Unsigned, Real, Octets, ObjectId };
    explicit SnmpValue(unsigned capacity)
        : kind(Empty), wireType(0), valid(false), hasLong(false), hasDouble(false),
          signedValue(0), unsignedValue(0), realValue(0), length(0), text(capacity, 0),
          bytes(capacity, 0)
    {
        oid.reserve(128);
    }

    Kind kind;
    unsigned char wireType;
    bool valid, hasLong, hasDouble;
    int64_t signedValue;
    uint64_t unsignedValue;
    double realValue;
    unsigned length;
    std::vector<char> text;
    std::vector<unsigned char> bytes;
    std::vector<uint32_t> oid;
};

#endif
