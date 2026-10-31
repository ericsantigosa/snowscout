#include "data.h"

// Persistent storage keys; the blob is stored in PERSIST_DATA_MAX_LENGTH chunks
#define KEY_BLOB_LEN 1
#define KEY_UPDATED 2
#define KEY_DAY0 3
#define KEY_BLOB_FIRST 10

SnowData g_snow;
static uint8_t s_blob[MAX_RESORTS * REC_SIZE];
static int s_blob_len;

static int16_t rd16(const uint8_t *p) {
  return (int16_t)(p[0] | (p[1] << 8));
}

static void parse(void) {
  g_snow.count = s_blob_len / REC_SIZE;
  for (int i = 0; i < g_snow.count; i++) {
    const uint8_t *p = s_blob + i * REC_SIZE;
    Resort *r = &g_snow.resorts[i];
    memcpy(r->name, p, NAME_BYTES);
    r->name[NAME_BYTES] = '\0';
    r->region = p[16] & 0x03;
    r->favourite = p[16] & 0x80;
    r->has_cam = p[16] & 0x40;
    r->tmin = (int8_t)p[17];
    r->alt = rd16(p + 18);
    r->drv = rd16(p + 20);
    r->f48 = rd16(p + 22);
    r->c72 = rd16(p + 24);
    r->lo = rd16(p + 26);
    r->hi = rd16(p + 28);
    r->m24 = rd16(p + 30);
    r->sd = rd16(p + 32);
    r->fl = rd16(p + 34);
    for (int d = 0; d < DAYS; d++) {
      r->daily[d] = rd16(p + 36 + 2 * d);
    }
  }
}

bool snow_set_blob(const uint8_t *blob, int len, time_t updated, time_t day0) {
  if (len % REC_SIZE != 0 || len > (int)sizeof(s_blob)) {
    return false;
  }
  memcpy(s_blob, blob, len);
  s_blob_len = len;
  g_snow.updated = updated;
  g_snow.day0 = day0;
  parse();
  return true;
}

static int chunk_len(int total, int off) {
  return total - off < PERSIST_DATA_MAX_LENGTH ? total - off : PERSIST_DATA_MAX_LENGTH;
}

void snow_save(void) {
  persist_write_int(KEY_BLOB_LEN, s_blob_len);
  persist_write_int(KEY_UPDATED, g_snow.updated);
  persist_write_int(KEY_DAY0, g_snow.day0);
  for (int off = 0, key = KEY_BLOB_FIRST; off < s_blob_len; off += PERSIST_DATA_MAX_LENGTH, key++) {
    persist_write_data(key, s_blob + off, chunk_len(s_blob_len, off));
  }
}

void snow_load(void) {
  int len = persist_read_int(KEY_BLOB_LEN);  // 0 when nothing is cached yet
  if (len <= 0 || len > (int)sizeof(s_blob) || len % REC_SIZE != 0) {
    return;
  }
  for (int off = 0, key = KEY_BLOB_FIRST; off < len; off += PERSIST_DATA_MAX_LENGTH, key++) {
    int n = chunk_len(len, off);
    if (persist_read_data(key, s_blob + off, n) != n) {
      return;
    }
  }
  s_blob_len = len;
  g_snow.updated = persist_read_int(KEY_UPDATED);
  g_snow.day0 = persist_read_int(KEY_DAY0);
  parse();
}

int16_t snow_value(const Resort *r, Board board) {
  switch (board) {
    case BOARD_FRESH48: return r->f48;
    case BOARD_DEPTH: return r->sd;
    default: return r->c72;
  }
}

const char *snow_board_title(Board board) {
  static const char *titles[BOARD_COUNT] = {"Next 72 h", "Fresh 48 h", "Snow depth"};
  return titles[board];
}

const char *snow_region_name(uint8_t region) {
  static const char *names[] = {"CAT", "AND", "FR", "?"};
  return names[region & 0x03];
}

void snow_fmt_cm(char *buf, size_t size, int16_t cm) {
  if (cm == NO_DATA) {
    snprintf(buf, size, "-");
  } else {
    snprintf(buf, size, "%d cm", cm);
  }
}

int snow_find(const char *name) {
  for (int pos = 0; pos < g_snow.count; pos++) {
    if (strcmp(g_snow.resorts[g_snow.order[pos]].name, name) == 0) {
      return pos;
    }
  }
  return -1;
}

// favourites first, then the board's value high to low (NO_DATA sorts last), then name
static bool before(const Resort *a, const Resort *b, Board board) {
  if (a->favourite != b->favourite) {
    return a->favourite;
  }
  int16_t va = snow_value(a, board);
  int16_t vb = snow_value(b, board);
  if (va != vb) {
    return va > vb;
  }
  return strcmp(a->name, b->name) < 0;
}

void snow_sort(Board board) {
  g_snow.board = board;
  g_snow.fav_count = 0;
  // insertion sort: at most MAX_RESORTS rows
  for (int i = 0; i < g_snow.count; i++) {
    int j = i;
    while (j > 0 && before(&g_snow.resorts[i], &g_snow.resorts[g_snow.order[j - 1]], board)) {
      g_snow.order[j] = g_snow.order[j - 1];
      j--;
    }
    g_snow.order[j] = i;
    if (g_snow.resorts[i].favourite) {
      g_snow.fav_count++;
    }
  }
}
