TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE
#=============================

#=============================
# Build the IOC application

PROD_IOC = nventSgp

#
# Pick up the net-snmp support
#
USR_CFLAGS += `net-snmp-config --cflags`
USR_LDFLAGS += `net-snmp-config --libs`
PROD_LDLIBS += `net-snmp-config --libs`

# nventSgp.dbd will be created and installed
DBD += nventSgp.dbd

# wienerCrateExample.dbd will be made up from these files:
nventSgp_DBD += base.dbd

# Include dbd files from all support applications:
nventSgp_DBD += devSnmp.dbd

# Add all the support libraries needed by this IOC
nventSgp_LIBS += devSnmp

# wienerCrateExample_registerRecordDeviceDriver.cpp derives from wienerCrateExample.dbd
nventSgp_SRCS += nventSgp_registerRecordDeviceDriver.cpp

# Build the main IOC entry point on workstation OSs.
nventSgp_SRCS_DEFAULT += nventSgpMain.cpp
nventSgp_SRCS_vxWorks += -nil-

# Add support from base/src/vxWorks if needed
#nventSgp_OBJS_vxWorks += $(EPICS_BASE_BIN)/vxComLibrary

# Finally link to the EPICS Base libraries
nventSgp_LIBS += $(EPICS_BASE_IOC_LIBS)

#===========================

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD RULES AFTER THIS LINE

