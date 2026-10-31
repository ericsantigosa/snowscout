#include "detail.h"
#include "data.h"

#define BAND_H 50
#define LABEL_H 16

static Window *s_window;
static Layer *s_canvas;
static int s_pos;
static char s_name[NAME_BYTES + 1];  // to find the same resort again after new data

static void text(GContext *ctx, const char *s, const char *font_key, GRect box, GTextAlignment align) {
  graphics_draw_text(ctx, s, fonts_get_system_font(font_key), box,
                     GTextOverflowModeTrailingEllipsis, align, NULL);
}

static void draw_bars(GContext *ctx, const Resort *r, GRect area) {
  static const char *weekdays[] = {"Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"};
  int base = area.origin.y + area.size.h - LABEL_H;  // bar baseline; day names below it
  int top = area.origin.y + LABEL_H;                 // room for the value over the tallest bar
  int slot = area.size.w / DAYS;
  int max = 10;                                      // so a 2 cm day stays a small bar
  for (int d = 0; d < DAYS; d++) {
    if (r->daily[d] != NO_DATA && r->daily[d] > max) {
      max = r->daily[d];
    }
  }
  int today = (int)((time(NULL) - g_snow.day0) / SECONDS_PER_DAY);

  graphics_context_set_stroke_color(ctx, GColorLightGray);
  graphics_draw_line(ctx, GPoint(area.origin.x, base), GPoint(area.origin.x + area.size.w - 1, base));
  for (int d = 0; d < DAYS; d++) {
    int x = area.origin.x + d * slot;
    int16_t v = r->daily[d];
    bool is_today = d == today;
    if (v != NO_DATA && v > 0) {
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
    time_t noon = g_snow.day0 + d * SECONDS_PER_DAY + SECONDS_PER_DAY / 2;
    const char *day = weekdays[localtime(&noon)->tm_wday];
    graphics_context_set_text_color(ctx, is_today ? GColorCobaltBlue : GColorDarkGray);
    text(ctx, day, is_today ? FONT_KEY_GOTHIC_14_BOLD : FONT_KEY_GOTHIC_14,
         GRect(x, base, slot, LABEL_H), GTextAlignmentCenter);
  }
}

static void draw(Layer *layer, GContext *ctx) {
  if (s_pos >= g_snow.count) {
    return;
  }
  const Resort *r = &g_snow.resorts[g_snow.order[s_pos]];
  GRect b = layer_get_bounds(layer);
  int w = b.size.w;
  char buf[48], a[10], c[10];

  graphics_context_set_fill_color(ctx, GColorOxfordBlue);
  graphics_fill_rect(ctx, GRect(0, 0, w, BAND_H), 0, GCornerNone);
  graphics_context_set_text_color(ctx, GColorWhite);
  text(ctx, r->name, FONT_KEY_GOTHIC_24_BOLD, GRect(6, -2, w - 12, 28), GTextAlignmentLeft);
  if (r->drv != NO_DATA) {
    snprintf(buf, sizeof(buf), "%d m · %s · %dh%02d drive", r->alt, snow_region_name(r->region),
             r->drv / 60, r->drv % 60);
  } else {
    snprintf(buf, sizeof(buf), "%d m · %s", r->alt, snow_region_name(r->region));
  }
  text(ctx, buf, FONT_KEY_GOTHIC_18, GRect(6, 24, w - 12, 22), GTextAlignmentLeft);

  draw_bars(ctx, r, GRect(4, BAND_H + 4, w - 8, 112));

  graphics_context_set_text_color(ctx, GColorBlack);
  if (r->c72 == NO_DATA) {
    snprintf(buf, sizeof(buf), "Next 72 h: no data");
  } else if (r->lo != NO_DATA && r->lo != r->hi) {
    snprintf(buf, sizeof(buf), "Next 72 h: %d cm (%d-%d)", r->c72, r->lo, r->hi);
  } else {
    snprintf(buf, sizeof(buf), "Next 72 h: %d cm", r->c72);
  }
  text(ctx, buf, FONT_KEY_GOTHIC_18_BOLD, GRect(6, 166, w - 12, 22), GTextAlignmentLeft);

  snow_fmt_cm(a, sizeof(a), r->f48);
  snow_fmt_cm(c, sizeof(c), r->sd);
  snprintf(buf, sizeof(buf), "Last 48 h: %s · depth %s", a, c);
  text(ctx, buf, FONT_KEY_GOTHIC_18, GRect(6, 186, w - 12, 22), GTextAlignmentLeft);

  buf[0] = '\0';
  if (r->tmin != INT8_MIN) {
    snprintf(buf, sizeof(buf), "min %d°C", r->tmin);
  }
  if (r->fl != NO_DATA) {
    int len = strlen(buf);
    snprintf(buf + len, sizeof(buf) - len, "%s0°C at %d m", len ? " · " : "", r->fl);
  }
  text(ctx, buf, FONT_KEY_GOTHIC_18, GRect(6, 205, w - 12, 22), GTextAlignmentLeft);
}

static void show(int pos) {
  s_pos = pos;
  strncpy(s_name, g_snow.resorts[g_snow.order[pos]].name, NAME_BYTES);
  if (s_canvas) {
    layer_mark_dirty(s_canvas);
  }
}

static void up_click(ClickRecognizerRef rec, void *ctx) {
  if (s_pos > 0) {
    show(s_pos - 1);
  }
}

static void down_click(ClickRecognizerRef rec, void *ctx) {
  if (s_pos < g_snow.count - 1) {
    show(s_pos + 1);
  }
}

static void click_config(void *ctx) {
  window_single_repeating_click_subscribe(BUTTON_ID_UP, 150, up_click);
  window_single_repeating_click_subscribe(BUTTON_ID_DOWN, 150, down_click);
}

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  s_canvas = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_canvas, draw);
  layer_add_child(root, s_canvas);
}

static void window_unload(Window *window) {
  layer_destroy(s_canvas);
  s_canvas = NULL;
}

void detail_push(int pos) {
  if (!s_window) {
    s_window = window_create();
    window_set_background_color(s_window, GColorWhite);
    window_set_click_config_provider(s_window, click_config);
    window_set_window_handlers(s_window, (WindowHandlers) {
      .load = window_load,
      .unload = window_unload,
    });
  }
  show(pos);
  window_stack_push(s_window, true);
}

void detail_refresh(void) {
  if (!s_canvas) {
    return;
  }
  int pos = snow_find(s_name);
  if (pos < 0) {
    window_stack_remove(s_window, true);  // the resort was hidden in settings
    return;
  }
  show(pos);
}

int detail_pos(void) {
  return s_pos;
}

void detail_deinit(void) {
  if (s_window) {
    window_destroy(s_window);
  }
}
