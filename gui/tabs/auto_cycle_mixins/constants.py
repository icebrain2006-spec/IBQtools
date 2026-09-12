"""Constants, register commands, and bitmask mappings for Auto Cycle & BQ Logger."""

# SBS Standard 16-bit Commands
SBS_COMMANDS = {
    "Temperature": (0x08, "degC", True),    # 0.1K to C
    "Voltage": (0x09, "mV", False),
    "Current": (0x0A, "mA", True),          # Signed
    "AverageCurrent": (0x0B, "mA", True),   # Signed
    "MaxError": (0x0C, "%", False),
    "RSOC": (0x0D, "%", False),
    "ASOC": (0x0E, "%", False),
    "RemainingCapacity": (0x0F, "mAh", False),
    "FullChargeCapacity": (0x10, "mAh", False),
    "RunTimeToEmpty": (0x11, "min", False),
    "ChargingCurrent": (0x14, "mA", False),
    "ChargingVoltage": (0x15, "mV", False),
    "BatteryStatus": (0x16, "hex", False),
    "CycleCount": (0x17, "cycle", False),
    "StateOfHealth": (0x4F, "%", False),
}

# 14 Status Registers for the Grid Matrix
STATUS_REGISTERS = [
    "Operation_A_HIGH", "Operation_A_LOW",
    "Operation_B_HIGH", "Operation_B_LOW",
    "Charging_HIGH", "Charging_LOW",
    "Gauging",
    "IT_HIGH", "IT_LOW",
    "Safety_AB_HIGH", "Safety_AB_LOW",
    "Safety_CD_HIGH", "Safety_CD_LOW",
    "Lstatus"
]

# 8 Bits per register (MSB to LSB: Bit 7 down to Bit 0)
REGISTER_BIT_NAMES = [
    ["SLEEP", "XCHG", "XDSG", "PF", "SS", "SDV", "SEC1", "SEC2"],
    ["BTP_INT", "EMSHUT", "FUSE", "ACTHR", "PCHG", "CHG", "DSG", "PRES"],
    ["IOSHUT", "PSSHUT", "DISCONN", "CB", "SLPCC", "VLB", "SMBLCAL", "INIT"],
    ["SLEEPM", "XL", "CAL_OFFSET", "CAL", "AUTOCALM", "AUTH", "LED", "SDM"],
    ["DEG1", "DEG0", "ERETM", "ERM", "NCT", "CCC", "CVR", "CCR"],
    ["VCT", "MCHG", "SU", "IN", "HV", "MV", "LV", "PV"],
    ["CF", "DSG", "EDV", "BAL_EN", "TC", "TD", "FC", "FD"],
    ["RSVD", "RSVD", "RSVD", "OCVFR", "LDMD", "RX", "QMAX", "VDQ"],
    ["NSFM", "OCVPRED", "SLPQMAX", "QEN", "VOK", "RDIS", "RSVD", "REST"],
    ["RSVD", "CUVC", "OTD", "OTC", "ASCDL", "ASCD", "ASCCL", "ASCC"],
    ["AOLDL", "AOLD", "OCD2", "OCD1", "OCC2", "OCC1", "COV", "CUV"],
    ["RSVD", "RSVD", "OCDL", "COVL", "UTD", "UTC", "PCHGC", "CHGV"],
    ["CHGC", "OC", "RSVD", "CTO", "RSVD", "PTO", "HWDF", "OTF"],
    ["RSVD", "RSVD", "RSVD", "RSVD", "FIELD_QMAX", "ITEN", "CF1", "CF0"]
]

# Auto Cycle Step Enum Strings
STEP_CHARGING = "CHARGING"
STEP_CHARGED = "CHARGED"
STEP_DISCHARGING = "DISCHARGING"
STEP_DISCHARGED = "DISCHARGED"
