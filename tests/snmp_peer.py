"""Controllable loopback SNMP transport boundary for the real IOC tests."""

import json
import socketserver
import threading
import time


def tlv(tag, value):
    size = len(value)
    length = bytes([size]) if size < 128 else bytes([0x82, size >> 8, size & 255])
    return bytes([tag]) + length + value


def integer(value):
    return tlv(2, value.to_bytes(8, "big", signed=True))


def items(data):
    offset = 0
    while offset < len(data):
        start = offset
        tag, size = data[offset:offset + 2]
        offset += 2
        if size & 128:
            count = size & 127
            size = int.from_bytes(data[offset:offset + count], "big")
            offset += count
        end = offset + size
        if end > len(data):
            raise ValueError("Truncated BER field")
        yield tag, data[offset:end], data[start:end]
        offset = end


def oid_bytes(numbers):
    result = bytearray([numbers[0] * 40 + numbers[1]])
    for number in numbers[2:]:
        encoded = [number & 127]
        number >>= 7
        while number:
            encoded.insert(0, 128 | (number & 127))
            number >>= 7
        result.extend(encoded)
    return bytes(result)


def oid_text(encoded):
    numbers = [min(encoded[0] // 40, 2)]
    numbers.append(encoded[0] - 40 * numbers[0])
    number = 0
    for byte in encoded[1:]:
        number = (number << 7) | (byte & 127)
        if not byte & 128:
            numbers.append(number)
            number = 0
    return "." + ".".join(str(part) for part in numbers)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        peer = self.server
        try:
            version, community, request = list(items(next(items(data))[1]))
            fields = list(items(request[1]))
            bindings = list(items(fields[3][1]))
            with peer.lock:
                reply, names, numeric, sets = [], [], [], []
                for _, binding, _ in bindings:
                    field_oid, field_value = list(items(binding))
                    oid = field_oid[1]
                    name = peer.names[oid]
                    names.append(name)
                    numeric.append(oid_text(oid))
                    if request[0] == 0xA3:
                        if field_value[0] == 2:
                            value = int.from_bytes(field_value[1], "big", signed=True)
                        elif field_value[0] == 4:
                            value = field_value[1].decode()
                        else:
                            raise ValueError("Unsupported SET type")
                        sets.append({"oid": oid_text(oid), "key": name,
                                     "type": field_value[0], "value": value})
                    value = peer.values[name]
                    encoded = integer(value) if isinstance(value, int) else tlv(4, value.encode())
                    if peer.mode == "exception":
                        encoded = tlv(0x80, b"")
                    reply.append(tlv(0x30, tlv(6, oid) + encoded))
                if peer.mode == "reverse":
                    reply.reverse()
                elif peer.mode == "missing":
                    reply = reply[1:]
                elif peer.mode == "duplicate":
                    reply += reply[:1]
                entry = {"time": time.monotonic_ns(), "event": "request", "pdu": request[0],
                         "version": int.from_bytes(version[1], "big"), "oids": names,
                         "community": community[1].decode(),
                         "numeric_oids": numeric, "sets": sets,
                         "id": int.from_bytes(fields[0][1], "big", signed=True)}
                peer.requests.append(entry)
                peer.record(entry)
                error = 17 if request[0] == 0xA3 and not peer.writable else (5 if peer.mode == "error" else 0)
                if request[0] == 0xA3 and not error:
                    for item in sets:
                        peer.values[item["key"]] = item["value"]
                    reply = [binding[2] for binding in bindings]
                response = tlv(0xA2, fields[0][2] + integer(error) + integer(0)
                               + tlv(0x30, b"".join(reply)))
                packet = tlv(0x30, version[2] + community[2] + response)
                if peer.mode == "drop":
                    return
                if peer.hold:
                    peer.held.append((packet, self.client_address, entry))
                    return
                sock.sendto(packet, self.client_address)
                peer.record(dict(entry, time=time.monotonic_ns(), event="response", error=error))
        except Exception as error:
            with peer.lock:
                peer.errors.append(repr(error))


class Peer(socketserver.ThreadingUDPServer):
    daemon_threads = True

    def __init__(self, evidence, writable=False):
        self.lock = threading.Lock()
        self.writable = writable
        self.values = {1: 101, 2: 202, 3: "hello", 4: 123}
        self.names = {oid_bytes((1, 3, 6, 1, 4, 1, 55555, n, 0)): n for n in self.values}
        self.requests, self.held, self.errors = [], [], []
        self.hold, self.mode = False, "normal"
        self.log = (evidence / "wire.jsonl").open("w")
        super().__init__(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    def release(self):
        with self.lock:
            packet, address, entry = self.held.pop(0)
            self.socket.sendto(packet, address)
            self.record(dict(entry, time=time.monotonic_ns(), event="response"))

    def record(self, entry):
        self.log.write(json.dumps(entry) + "\n")
        self.log.flush()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join()
        self.log.close()
