#include <pebble.h>

// Snowscout Face: time, date, the biggest daily snowfall of the next 7 days at any resort,
// the 72 h leader and the next big day. The phone sends a summary (src/pkjs/index.js).

#define KEY_SUMMARY 1
#define DAYS 7
#define STALE_AFTER (6 * SECONDS_PER_HOUR)
#define REFRESH_EVERY (30 * SECONDS_PER_MINUTE)
#define BAND_H 90
#define LABEL_H 16

typedef struct {
  int32_t updated;      // when the backend ran, 0 = no data yet
  int32_t day0;         // local midnight of week[0]
  uint8_t week[DAYS];   // biggest daily total at any resort, cm
  char line_a[32];      // 72 h leader, e.g. "Baqueira 38 cm"
  char line_b[40];      // next big day, e.g. "Sat: Arcalís 22 cm"
} Summary;

static Window *s_window;
static Layer *s_canvas;
static Summary s_sum;
static time_t s_last_request;

static void text(GContext *ctx, const char *s, const char *font_key, GRect box, GTextAlignment align) {
  graphics_draw_text(ctx, s, fonts_get_system_font(font_key), box,
                     GTextOverflowModeTrailingEllipsis, align, NULL);
}

static void draw_week(GContext *ctx, GRect area, time_t now) {
  static const char *weekdays[] = {"Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"};
  int base = area.origin.y + area.size.h - LABEL_H;
  int top = area.origin.y + LABEL_H;
  int slot = area.size.w / DAYS;
  int max = 10;
  for (int d = 0; d < DAYS; d++) {
    if (s_sum.week[d] > max) {
      max = s_sum.week[d];
    }
  }
  int today = (int)((now - s_sum.day0) / SECONDS_PER_DAY);

  graphics_context_set_stroke_color(ctx, GColorLightGray);
  graphics_draw_line(ctx, GPoint(area.origin.x, base), GPoint(area.origin.x + area.size.w - 1, base));
  for (int d = 0; d < DAYS; d++) {
    int x = area.origin.x + d * slot;
    bool is_today = d == today;
    int v = s_sum.week[d];
    if (v > 0) {
      int h = v * (base - top) / max;
      if (h < 2) {
        h = 2;
      }
      graphics_context_set_fill_color(ctx, is_today ? GColorVividCerulean : GColorPictonBlue);
      graphics_fill_rect(ctx, GRect(x + 4, base - h, slot - 8, h), 2, GCornersTop);
      char num[6];
      snprintf(num, sizeof(num), "%d", v);
      graphics_context_set_text_color(ctx, GColorBlack);
      text(ctx, num, FONT_KEY_GOTHIC_14, GRect(x, base - h - LABEL_H - 2, slot, LABEL_H), GTextAlignmentCenter);
    }
    time_t noon = s_sum.day0 + d * SECONDS_PER_DAY + SECONDS_PER_DAY / 2;
    graphics_context_set_text_color(ctx, is_today ? GColorCobaltBlue : GColorDarkGray);
    text(ctx, weekdays[localtime(&noon)->tm_wday], is_today ? FONT_KEY_GOTHIC_14_BOLD : FONT_KEY_GOTHIC_14,
         GRect(x, base, slot, LABEL_H), GTextAlignmentCenter);
  }
}

static void draw(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  int w = b.size.w;
  time_t now = time(NULL);
  char clock[8], date[16];
  struct tm *t = localtime(&now);
  strftime(clock, sizeof(clock), clock_is_24h_style() ? "%H:%M" : "%I:%M", t);
  strftime(date, sizeof(date), "%a %d %b", t);

  graphics_context_set_fill_color(ctx, GColorOxfordBlue);
  graphics_fill_rect(ctx, GRect(0, 0, w, BAND_H), 0, GCornerNone);
  graphics_context_set_text_color(ctx, GColorWhite);
  bool drop_zero = !clock_is_24h_style() && clock[0] == '0';  // "09:41" -> "9:41" in 12 h style
  text(ctx, drop_zero ? clock + 1 : clock, FONT_KEY_LECO_42_NUMBERS, GRect(0, 8, w, 48),
       GTextAlignmentCenter);
  graphics_context_set_text_color(ctx, GColorCeleste);
  text(ctx, date, FONT_KEY_GOTHIC_24_BOLD, GRect(0, 56, w, 28), GTextAlignmentCenter);

  if (!s_sum.updated) {
    graphics_context_set_text_color(ctx, GColorDarkGray);
    text(ctx, "Waiting for snow data...", FONT_KEY_GOTHIC_18, GRect(6, 150, w - 12, 22), GTextAlignmentCenter);
    return;
  }

  draw_week(ctx, GRect(4, BAND_H + 2, w - 8, 62), now);

  graphics_context_set_text_color(ctx, GColorDarkGray);
  text(ctx, "Next 72 h", FONT_KEY_GOTHIC_14, GRect(6, 158, w - 12, 16), GTextAlignmentLeft);
  graphics_context_set_text_color(ctx, GColorBlack);
  text(ctx, s_sum.line_a, FONT_KEY_GOTHIC_24_BOLD, GRect(6, 168, w - 12, 28), GTextAlignmentLeft);

  int age = now - s_sum.updated;
  char stale[24];
  if (age > STALE_AFTER) {
    snprintf(stale, sizeof(stale), "data %d h old", age / SECONDS_PER_HOUR);
    graphics_context_set_text_color(ctx, GColorDarkCandyAppleRed);
  } else {
    graphics_context_set_text_color(ctx, GColorCobaltBlue);
  }
  text(ctx, age > STALE_AFTER ? stale : s_sum.line_b, FONT_KEY_GOTHIC_18, GRect(6, 198, w - 12, 22),
       GTextAlignmentLeft);
}

static void request_refresh(void) {
  DictionaryIterator *out;
  if (app_message_outbox_begin(&out) == APP_MSG_OK) {
    dict_write_uint8(out, MESSAGE_KEY_REFRESH, 1);
    app_message_outbox_send();
  }
  s_last_request = time(NULL);
}

static void tick(struct tm *now, TimeUnits changed) {
  layer_mark_dirty(s_canvas);
  if (time(NULL) - s_last_request >= REFRESH_EVERY) {
    request_refresh();
  }
}

static void copy_string(char *dst, size_t size, Tuple *t) {
  if (t) {
    snprintf(dst, size, "%s", t->value->cstring);
  }
}

static void inbox_received(DictionaryIterator *iter, void *ctx) {
  Tuple *updated = dict_find(iter, MESSAGE_KEY_TIME);
  Tuple *day0 = dict_find(iter, MESSAGE_KEY_DAY0);
  Tuple *week = dict_find(iter, MESSAGE_KEY_WEEK);
  if (!updated || !day0 || !week || week->length != DAYS) {
    return;
  }
  s_sum.updated = updated->value->int32;
  s_sum.day0 = day0->value->int32;
  memcpy(s_sum.week, week->value->data, DAYS);
  copy_string(s_sum.line_a, sizeof(s_sum.line_a), dict_find(iter, MESSAGE_KEY_LINE_A));
  copy_string(s_sum.line_b, sizeof(s_sum.line_b), dict_find(iter, MESSAGE_KEY_LINE_B));
  persist_write_data(KEY_SUMMARY, &s_sum, sizeof(s_sum));
  s_last_request = time(NULL);  // the phone just fetched; the next refresh is due in 30 min
  layer_mark_dirty(s_canvas);
}

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  s_canvas = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_canvas, draw);
  layer_add_child(root, s_canvas);
}

static void window_unload(Window *window) {
  layer_destroy(s_canvas);
}

static void init(void) {
  if (persist_read_data(KEY_SUMMARY, &s_sum, sizeof(s_sum)) != sizeof(s_sum)) {
    memset(&s_sum, 0, sizeof(s_sum));
  }
  s_last_request = time(NULL);  // the phone fetches on its own when the face starts

  s_window = window_create();
  window_set_background_color(s_window, GColorWhite);
  window_set_window_handlers(s_window, (WindowHandlers) {
    .load = window_load,
    .unload = window_unload,
  });
  window_stack_push(s_window, true);

  app_message_register_inbox_received(inbox_received);
  app_message_open(256, 64);
  tick_timer_service_subscribe(MINUTE_UNIT, tick);
}

static void deinit(void) {
  tick_timer_service_unsubscribe();
  window_destroy(s_window);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
