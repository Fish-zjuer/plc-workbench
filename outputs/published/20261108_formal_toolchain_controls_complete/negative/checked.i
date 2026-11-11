typedef _Bool bool;
enum { false = 0, true = 1 };
typedef signed char int8_t; typedef unsigned char uint8_t;
typedef short int16_t; typedef unsigned short uint16_t;
typedef int int32_t; typedef unsigned int uint32_t;
typedef long long int64_t; typedef unsigned long long uint64_t;
_Static_assert(sizeof(int8_t)==1 && sizeof(int16_t)==2 && sizeof(int32_t)==4 && sizeof(int64_t)==8, "PLC integer widths");
_Static_assert(sizeof(float)==4 && sizeof(double)==8, "PLC float widths");
double sqrt(double); double sin(double); double cos(double); double tan(double);
double exp(double); double log(double); double pow(double,double); double fabs(double);
double floor(double); double ceil(double); double round(double);
void assert(bool value) { __CPROVER_assert(value, "PLC assertion"); }




// Struct definitions
typedef struct {
	bool Maintenance;
	bool CalibDone;
	bool MeasureReq;
	uint8_t State;
	bool CalibReq;
	bool MaintLamp;
	bool MeasurePermit;
	uint8_t preState;
} __FB_SpectrometerQualification;

typedef struct { unsigned char pvl_empty; } __VerificationLoopDS;

typedef struct {
	bool Maintenance;
	bool CalibDone;
	bool MeasureReq;
	uint8_t State;
	bool CalibReq;
	bool MaintLamp;
	bool MeasurePermit;
	__FB_SpectrometerQualification PVL_Uut;
	uint8_t PVL_S;
	uint8_t PVL_PreS;
	int32_t PVL_Scan;
	bool PVL_Active;
	bool PVL_Done;
	int32_t PVL_DtMs;
	int32_t PVL_NowMs;
	bool PVL_A0;
	bool PVL_A1;
	bool PVL_A2;
	bool PVL_A3;
	bool PVL_A4;
	bool PVL_A5;
	bool PVL_A6;
	bool PVL_A7;
	bool PVL_A8;
	bool PVL_A9;
} __PVL_Harness;

// Global variables
__PVL_Harness instance;
__VerificationLoopDS verificationLoop;
bool EoC;
bool BoC;
bool __cbmc_boc_marker;
bool __cbmc_eoc_marker;

// Forward declarations of the generated functions
void FB_SpectrometerQualification(__FB_SpectrometerQualification *__context);
void PVL_Harness(__PVL_Harness *__context);
void VerificationLoop();

// Declare nondet assignment functions
bool nondet_bool(void);
uint8_t nondet_uint8_t(void);
uint16_t nondet_uint16_t(void);
uint32_t nondet_uint32_t(void);
uint64_t nondet_uint64_t(void);
int8_t nondet_int8_t(void);
int16_t nondet_int16_t(void);
int32_t nondet_int32_t(void);
int64_t nondet_int64_t(void);
float nondet_float(void);
double nondet_double(void);

// Translated functions
void FB_SpectrometerQualification(__FB_SpectrometerQualification *__context) {
	// Temporary variables

	{
		__context->preState = __context->State;
		if (__context->Maintenance) {
			__context->State = 2;
		}
		else if ((__context->preState == 2)) {
			__context->State = 1;
		}
		else if (((__context->preState == 0) && __context->CalibDone)) {
			__context->State = 1;
		}
		else {
			__context->State = __context->preState;
		}
		__context->CalibReq = (__context->State == 0);
		__context->MaintLamp = (__context->State == 2);
		__context->MeasurePermit = (__context->MeasureReq && (__context->State == 1));
		return;
	}
}

void PVL_Harness(__PVL_Harness *__context) {
	// Temporary variables

	{
		if ((__context->PVL_Scan < 3)) {
			__context->PVL_NowMs = (__context->PVL_NowMs + __context->PVL_DtMs);
			// Assign inputs
			__context->PVL_Uut.Maintenance = __context->Maintenance;
			__context->PVL_Uut.CalibDone = __context->CalibDone;
			__context->PVL_Uut.MeasureReq = __context->MeasureReq;
			FB_SpectrometerQualification(&__context->PVL_Uut);
			// Assign outputs
			__context->State = __context->PVL_Uut.State;
			__context->CalibReq = __context->PVL_Uut.CalibReq;
			__context->MaintLamp = __context->PVL_Uut.MaintLamp;
			__context->MeasurePermit = __context->PVL_Uut.MeasurePermit;
			__context->PVL_PreS = __context->PVL_S;
			if (__context->Maintenance) {
				__context->PVL_S = 2;
			}
			else if ((__context->PVL_PreS == 2)) {
				__context->PVL_S = 0;
			}
			else if (((__context->PVL_PreS == 0) && __context->CalibDone)) {
				__context->PVL_S = 1;
			}
			if ((__context->PVL_Scan <= 3)) {
				__context->PVL_Scan = (__context->PVL_Scan + 1);
			}
			__context->PVL_Active = (__context->PVL_Scan <= 3);
			__context->PVL_Done = (__context->PVL_Scan >= 3);
			__context->PVL_A0 = (__context->State == __context->PVL_S);
			__context->PVL_A1 = ((! __context->Maintenance) || (__context->State == 2));
			__context->PVL_A2 = ((! ((! __context->Maintenance) && (__context->PVL_PreS == 2))) || (__context->State == 0));
			__context->PVL_A3 = ((! (((! __context->Maintenance) && (__context->PVL_PreS == 0)) && __context->CalibDone)) || (__context->State == 1));
			__context->PVL_A4 = ((! (((! __context->Maintenance) && (__context->PVL_PreS == 0)) && (! __context->CalibDone))) || (__context->State == 0));
			__context->PVL_A5 = ((! ((! __context->Maintenance) && (__context->PVL_PreS == 1))) || (__context->State == 1));
			__context->PVL_A6 = (__context->CalibReq == (__context->State == 0));
			__context->PVL_A7 = (__context->MaintLamp == (__context->State == 2));
			__context->PVL_A8 = (__context->MeasurePermit == (__context->MeasureReq && (__context->State == 1)));
			__context->PVL_A9 = (((__context->State == 0) || (__context->State == 1)) || (__context->State == 2));
		}
		else {
			__context->PVL_Active = false;
			__context->PVL_Done = true;
		}
		return;
	}
}

int pvl_tick;
bool pvl_domain = true;
bool pvl_invariant_P01 = true;
bool pvl_invariant_P02 = true;
bool pvl_invariant_P03 = true;
bool pvl_invariant_P04 = true;
bool pvl_invariant_P05 = true;
bool pvl_invariant_P06 = true;
bool pvl_invariant_P07 = true;
bool pvl_invariant_P08 = true;
bool pvl_invariant_P09 = true;
bool pvl_invariant_P10 = true;
void VerificationLoop() {
	// Temporary variables

	{
		for (pvl_tick = 0; pvl_tick < 3; ++pvl_tick) {
			instance.CalibDone = nondet_bool();
			instance.Maintenance = nondet_bool();
			instance.MeasureReq = nondet_bool();
			BoC = true;
			VerificationLoop_prepare_BoC: {
				__cbmc_boc_marker = true; // to indicate the beginning of the loop for the counterexample parser
				__cbmc_boc_marker = false;
			}
			BoC = false;
			// Assign inputs
			PVL_Harness(&instance);
			// Assign outputs
			EoC = true;
			VerificationLoop_prepare_EoC: {
pvl_invariant_P01 = pvl_invariant_P01 && instance.PVL_A0;
pvl_invariant_P02 = pvl_invariant_P02 && instance.PVL_A1;
pvl_invariant_P03 = pvl_invariant_P03 && instance.PVL_A2;
pvl_invariant_P04 = pvl_invariant_P04 && instance.PVL_A3;
pvl_invariant_P05 = pvl_invariant_P05 && instance.PVL_A4;
pvl_invariant_P06 = pvl_invariant_P06 && instance.PVL_A5;
pvl_invariant_P07 = pvl_invariant_P07 && instance.PVL_A6;
pvl_invariant_P08 = pvl_invariant_P08 && instance.PVL_A7;
pvl_invariant_P09 = pvl_invariant_P09 && instance.PVL_A8;
pvl_invariant_P10 = pvl_invariant_P10 && instance.PVL_A9;

				__cbmc_eoc_marker = true; // to indicate the end of the loop for the counterexample parser
				__cbmc_eoc_marker = false;
			}
			EoC = false;
		}
__CPROVER_assert(!pvl_domain || pvl_invariant_P01, "PVL:LTL:P01");
__CPROVER_assert(!pvl_domain || pvl_invariant_P02, "PVL:LTL:P02");
__CPROVER_assert(!pvl_domain || pvl_invariant_P03, "PVL:LTL:P03");
__CPROVER_assert(!pvl_domain || pvl_invariant_P04, "PVL:LTL:P04");
__CPROVER_assert(!pvl_domain || pvl_invariant_P05, "PVL:LTL:P05");
__CPROVER_assert(!pvl_domain || pvl_invariant_P06, "PVL:LTL:P06");
__CPROVER_assert(!pvl_domain || pvl_invariant_P07, "PVL:LTL:P07");
__CPROVER_assert(!pvl_domain || pvl_invariant_P08, "PVL:LTL:P08");
__CPROVER_assert(!pvl_domain || pvl_invariant_P09, "PVL:LTL:P09");
__CPROVER_assert(!pvl_domain || pvl_invariant_P10, "PVL:LTL:P10");
return;
	}
}

// Entry point
int main(void) {
	// Initial values
	instance.Maintenance = false;
	instance.CalibDone = false;
	instance.MeasureReq = false;
	instance.State = 0;
	instance.CalibReq = false;
	instance.MaintLamp = false;
	instance.MeasurePermit = false;
	instance.PVL_Uut.Maintenance = false;
	instance.PVL_Uut.CalibDone = false;
	instance.PVL_Uut.MeasureReq = false;
	instance.PVL_Uut.State = 0;
	instance.PVL_Uut.CalibReq = true;
	instance.PVL_Uut.MaintLamp = false;
	instance.PVL_Uut.MeasurePermit = false;
	instance.PVL_Uut.preState = 0;
	instance.PVL_S = 0;
	instance.PVL_PreS = 0;
	instance.PVL_Scan = 0;
	instance.PVL_Active = false;
	instance.PVL_Done = false;
	instance.PVL_DtMs = 10;
	instance.PVL_NowMs = -10;
	instance.PVL_A0 = false;
	instance.PVL_A1 = false;
	instance.PVL_A2 = false;
	instance.PVL_A3 = false;
	instance.PVL_A4 = false;
	instance.PVL_A5 = false;
	instance.PVL_A6 = false;
	instance.PVL_A7 = false;
	instance.PVL_A8 = false;
	instance.PVL_A9 = false;
	EoC = false;
	BoC = false;

	// Custom entry logic
	VerificationLoop();

	return 0;
}

