TOP=../..
include $(TOP)/configure/CONFIG
SRC_DIRS += $(TOP)/snmpApp/src
PROD_IOC += snmpRequestTest
DBD += snmpRequestTest.dbd
snmpRequestTest_DBD += base.dbd devSnmp.dbd sequenceProbe.dbd nativeProbe.dbd
snmpRequestTest_SRCS += snmpRequestTest_registerRecordDeviceDriver.cpp sequenceProbe.cpp nativeProbe.cpp
snmpRequestTest_SRCS_DEFAULT += snmpMain.cpp
snmpRequestTest_LIBS += devSnmp $(EPICS_BASE_IOC_LIBS)
include $(TOP)/configure/RULES
