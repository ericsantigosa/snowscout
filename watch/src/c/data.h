#pragma once
#include <pebble.h>

// One resort record as packed by src/pkjs/index.js (pack)
#define REC_SIZE 66
#define NAME_BYTES 16
#define MAX_RESORTS 40
#define DAYS 7
#define NO_DATA INT16_MIN
#define NO_COUNT 0xFF
#define COLOURS 4                         // green, blue, red, black

typedef enum { BOARD_NEXT72, BOARD_FRESH48, BOARD_DEPTH, BOARD_OPEN, BOARD_COUNT } Board;
typedef enum { REP_NONE, REP_OPEN, REP_CLOSED } ReportState;

typedef struct {
  char name[NAME_BYTES + 1];
  uint8_t region;                         // 0 Catalonia, 1 Andorra, 2 France
  bool favourite;
  bool has_cam;                           // the phone knows a webcam URL for it
  int8_t tmin;                            // min temp next 24 h, INT8_MIN = no data
  int16_t alt, drv;                       // mid-mountain altitude (m), drive (min)
  int16_t f48, c72, lo, hi, m24, sd, fl;  // cm (fl in m), NO_DATA when missing
  int16_t daily[DAYS];                    // cm per local day; daily[0] starts at day0
  int8_t av;                              // avalanche danger 1-5, 0 = no snow, -1 = no rating
  uint8_t rep;                            // ReportState of the official snow report
  uint8_t lifts[2], slopes[2];            // open, total; NO_COUNT when unknown
  uint8_t col[COLOURS][2];                // slopes per colour: open, total
  uint16_t opens;                         // opening day (days since 1970-01-01), 0 = unknown
} Resort;

typedef struct {
  Resort resorts[MAX_RESORTS];
  int count;
  time_t updated;                         // when the backend ran
  time_t day0;                            // local midnight of daily[0]
  Board board;
  int order[MAX_RESORTS];                 // display order for `board`: favourites first
  int fav_count;
} SnowData;

extern SnowData g_snow;

bool snow_set_blob(const uint8_t *blob, int len, time_t updated, time_t day0);
void snow_save(void);
void snow_load(void);
void snow_sort(Board board);
int16_t snow_value(const Resort *r, Board board);
const char *snow_board_title(Board board);
const char *snow_region_name(uint8_t region);
void snow_fmt_cm(char *buf, size_t size, int16_t cm);
int snow_find(const char *name);  // position in order[], or -1
