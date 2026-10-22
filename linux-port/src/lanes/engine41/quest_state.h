#ifndef TITBIT_QUEST_STATE_H
#define TITBIT_QUEST_STATE_H

// Original 0x198-byte state block, written verbatim by SaveGame.
class QuestState {
public:
 char header[0x2c];
 int vars[89];
 int tail[2];
 QuestState();
 ~QuestState();
 void Reset_0041e630();
 int SaveGame_0041e590(const char *file);
 int LoadGame_0041e5e0(const char *file);
};

extern QuestState g_005024b0;
#endif
