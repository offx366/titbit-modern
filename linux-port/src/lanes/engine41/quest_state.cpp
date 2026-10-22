// Quest state block (0x198 bytes, global at 0x5024b0) saved verbatim to disk,
// and the save-slot time stamp helpers.
#include <stdio.h>
#include <string.h>
#include "quest_state.h"
extern "C" __declspec(dllimport) void __stdcall GetLocalTime(struct _SYSTEMTIME *);
struct _SYSTEMTIME { unsigned short wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute, wSecond, wMilliseconds; };

QuestState::QuestState() { Reset_0041e630(); }

void QuestState::Reset_0041e630() {
 vars[0] = 0;
 vars[1] = 0;
 vars[2] = 0;
 vars[3] = 0;
 vars[4] = 0;
 vars[5] = 0;
 vars[6] = 0;
 vars[7] = 0;
 vars[8] = 0;
 vars[9] = 0;
 vars[10] = 0;
 vars[11] = 0;
 vars[12] = 0;
 vars[13] = 0;
 vars[14] = 0;
 vars[15] = 0;
 vars[16] = 0;
 vars[17] = 0;
 vars[18] = 0;
 vars[19] = 0;
 vars[20] = 0;
 vars[21] = 0;
 vars[22] = 0;
 vars[23] = 0;
 vars[24] = 0;
 vars[25] = 0;
 vars[26] = 0;
 vars[27] = 0;
 vars[28] = 0;
 vars[29] = 0;
 vars[30] = 0;
 vars[31] = 0;
 vars[32] = 0;
 vars[33] = 0;
 vars[34] = 0;
 vars[35] = 0;
 vars[36] = 0;
 vars[37] = 0;
 vars[38] = 0;
 vars[39] = 0;
 vars[40] = 0;
 vars[41] = 0;
 vars[42] = 0;
 vars[43] = 0;
 vars[44] = 0;
 vars[45] = 0;
 vars[46] = 0;
 vars[47] = 0;
 vars[48] = 0;
 vars[49] = 0;
 vars[50] = 0;
 vars[51] = 0;
 vars[52] = 0;
 vars[53] = 0;
 vars[54] = 0;
 vars[55] = 0;
 vars[56] = 0;
 vars[57] = 0;
 vars[58] = 0;
 vars[59] = 0;
 vars[60] = 0;
 vars[61] = 0;
 vars[62] = 0;
 vars[63] = 0;
 vars[64] = 0;
 vars[65] = 0;
 vars[66] = 0;
 vars[67] = 0;
 vars[68] = 0;
 vars[69] = 0;
 vars[70] = 0;
 vars[71] = 0;
 vars[72] = 0;
 vars[73] = 0;
 vars[74] = 0;
 vars[75] = 0;
 vars[76] = 0;
 vars[77] = 0;
 vars[78] = 0;
 vars[79] = 0;
 vars[80] = 0;
 vars[81] = 0;
 vars[82] = 0;
 vars[83] = 0;
 vars[84] = 0;
 vars[85] = 0;
 vars[86] = 0;
 vars[87] = 0;
 vars[88] = 0;
}

int QuestState::SaveGame_0041e590(const char *file) {
 FILE *f = fopen(file, "wb");
 if (f) {
  fwrite(this, 1, sizeof(*this), f);
  fclose(f);
  return 1;
 }
 return 0;
}

int QuestState::LoadGame_0041e5e0(const char *file) {
 FILE *f = fopen(file, "rb");
 if (f) {
  fread(this, 1, sizeof(*this), f);
  fclose(f);
  return 1;
 }
 return 0;
}

QuestState g_005024b0;

// 32-byte save-slot caption.
struct SaveStamp { // original 0x41e810
 char text[32];
 void GetTime_0041e810();
 void GetTimeFromFile_0041e890(const char *file);
};

void SaveStamp::GetTime_0041e810() {
 _SYSTEMTIME st;
 GetLocalTime(&st);
 memset(text, 0, sizeof(text));
 sprintf(text, "%.2d-%.2d-%.2d %.2d:%.2d:%.2d", st.wDay, st.wMonth, st.wYear, st.wHour, st.wMinute, st.wSecond);
}

void SaveStamp::GetTimeFromFile_0041e890(const char *file) {
 memset(text, 0, sizeof(text));
 FILE *f = fopen(file, "rb");
 if (f) {
  fread(text, 1, sizeof(text), f);
  fclose(f);
  return;
 }
 sprintf(text, "empty");
}
