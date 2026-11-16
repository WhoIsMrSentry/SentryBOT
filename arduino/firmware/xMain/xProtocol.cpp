#include "xProtocol.h"

// Single-definition of static members used by Protocol
String Protocol::buf;
long Protocol::currentSeq = -1;
bool Protocol::hasCurrentSeq = false;
uint32_t Protocol::i2cErrors = 0;
