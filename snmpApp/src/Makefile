TOP=../..
include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE
#=============================


USR_CFLAGS += $(shell $(PERL) ../getNetSNMPversion.pl)
USR_CPPFLAGS += $(shell $(PERL) ../getNetSNMPversion.pl)

#==================================================
# Build an IOC support library
LIBRARY_IOC += devSnmp

# xxxRecord.h will be created from xxxRecord.dbd
#DBDINC += xxxRecord
# install devXxxSoft.dbd into <top>/dbd
DBD += devSnmp.dbd

# The following are compiled and added to the Support library

devSnmp_SRCS += snmpRegister.cpp
devSnmp_SRCS += snmpSessShow.c
devSnmp_SRCS += devSnmp.cpp

devSnmp_LIBS += $(EPICS_BASE_IOC_LIBS)




#=============================
# build an ioc application

PROD_IOC = snmp
# snmp.dbd will be created and installed
DBD += snmp.dbd

snmp_DBD += base.dbd
snmp_DBD += devSnmp.dbd

# <name>_registerRecordDeviceDriver.cpp will be created from <name>.dbd
snmp_SRCS += snmp_registerRecordDeviceDriver.cpp

snmp_SRCS_DEFAULT += snmpMain.cpp

snmp_LIBS += devSnmp

snmp_LIBS += $(EPICS_BASE_IOC_LIBS)

#===========================

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD RULES AFTER THIS LINE

