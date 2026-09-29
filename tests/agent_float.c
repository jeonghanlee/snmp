/* Writable Opaque float scalar served by the real Net-SNMP agent. */
#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <net-snmp/agent/net-snmp-agent-includes.h>

static float value = 12.5f;
static oid object_id[] = {1, 3, 6, 1, 4, 1, 55556, 9};

void init_fixtureFloat(void)
{
    netsnmp_handler_registration *registration = netsnmp_create_handler_registration(
        "fixtureFloat", NULL, object_id, OID_LENGTH(object_id), HANDLER_CAN_RWRITE);
    netsnmp_watcher_info *watcher = netsnmp_create_watcher_info(
        &value, sizeof(value), ASN_OPAQUE_FLOAT, WATCHER_FIXED_SIZE);
    if (!registration || !watcher || netsnmp_register_watched_scalar(registration, watcher) != MIB_REGISTERED_OK)
        snmp_log(LOG_ERR, "fixtureFloat registration failed\n");
}
