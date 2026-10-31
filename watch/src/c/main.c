#include <pebble.h>
#include "cam.h"
#include "data.h"
#include "detail.h"

#define KEY_BOARD 20             // persisted first board (set from the phone settings page)
#define STALE_AFTER (6 * SECONDS_PER_HOUR)
#define HEADER_ROW_H 52
#define RESORT_ROW_H 50

static Window *s_window;
static MenuLayer *s_menu;
static char s_status[48];        // problem reported by the phone, shown in the header
static bool s_back_from_detail;

static void text(GContext *ctx, const char *s, const char *font_key, GRect box, GTextAlignment align) {
  graphics_draw_text(ctx, s, fonts_get_system_font(font_key), box,
                     GTextOverflowModeTrailingEllipsis, align, NULL);
}

// Menu layout: section 0 holds the board header row; then favourites (if any); then the rest.
static bool is_fav_section(uint16_t section) {
  return g_snow.fav_count && section == 1;
}

static int row_pos(MenuIndex *index) {
  return is_fav_section(index->section) ? index->row : g_snow.fav_count + index->row;
}

static MenuIndex pos_index(int pos) {
  if (pos < g_snow.fav_count) {
    return MenuIndex(1, pos);
  }
  return MenuIndex(g_snow.fav_count ? 2 : 1, pos - g_snow.fav_count);
}

static void next_board(void) {
  snow_sort((g_snow.board + 1) % BOARD_COUNT);
  menu_layer_reload_data(s_menu);
}

static void fmt_age(char *buf, size_t size) {
  if (!g_snow.updated) {
    snprintf(buf, size, "%s", s_status[0] ? s_status : "Loading...");
    return;
  }
  int mins = (time(NULL) - g_snow.updated) / 60;
  if (mins < 0) {
    mins = 0;
  }
  const char *what = s_status[0] ? "offline, data from" : "updated";
  if (mins < 60) {
    snprintf(buf, size, "%s %d min ago", what, mins);
  } else {
    snprintf(buf, size, "%s %d h ago", what, mins / 60);
  }
}

static void draw_board_header(GContext *ctx, const Layer *cell, bool highlighted) {
  GRect b = layer_get_bounds(cell);
  if (!highlighted) {
    graphics_context_set_fill_color(ctx, GColorCeleste);
    graphics_fill_rect(ctx, b, 0, GCornerNone);
  }
  char count[8], age[48];
  snprintf(count, sizeof(count), "%d/%d", g_snow.board + 1, BOARD_COUNT);
  fmt_age(age, sizeof(age));
  bool stale = g_snow.updated && time(NULL) - g_snow.updated > STALE_AFTER;

  graphics_context_set_text_color(ctx, highlighted ? GColorWhite : GColorBlack);
  text(ctx, snow_board_title(g_snow.board), FONT_KEY_GOTHIC_24_BOLD, GRect(6, -2, b.size.w - 50, 28),
       GTextAlignmentLeft);
  text(ctx, count, FONT_KEY_GOTHIC_18, GRect(b.size.w - 46, 2, 40, 22), GTextAlignmentRight);
  graphics_context_set_text_color(ctx, highlighted ? GColorWhite
                                  : (stale || s_status[0]) ? GColorDarkCandyAppleRed : GColorDarkGray);
  text(ctx, age, FONT_KEY_GOTHIC_18, GRect(6, 24, b.size.w - 12, 22), GTextAlignmentLeft);
}

static void draw_resort(GContext *ctx, const Layer *cell, const Resort *r, bool highlighted) {
  GRect b = layer_get_bounds(cell);
  char value[10], sub[48], a[10], c[10];
  snow_fmt_cm(value, sizeof(value), snow_value(r, g_snow.board));
  switch (g_snow.board) {
    case BOARD_FRESH48:
      snow_fmt_cm(a, sizeof(a), r->c72);
      snow_fmt_cm(c, sizeof(c), r->sd);
      snprintf(sub, sizeof(sub), "next 72 h %s · depth %s", a, c);
      break;
    case BOARD_DEPTH:
      snow_fmt_cm(a, sizeof(a), r->f48);
      snow_fmt_cm(c, sizeof(c), r->c72);
      snprintf(sub, sizeof(sub), "fresh %s · next %s", a, c);
      break;
    default:
      if (r->lo == NO_DATA) {
        snprintf(sub, sizeof(sub), "no forecast");
      } else if (r->hi == 0) {
        snprintf(sub, sizeof(sub), "no snow in any model");
      } else if (r->lo == r->hi) {
        snprintf(sub, sizeof(sub), "24 h max %d", r->m24);
      } else {
        snprintf(sub, sizeof(sub), "24 h max %d · models %d-%d", r->m24, r->lo, r->hi);
      }
      break;
  }
  graphics_context_set_text_color(ctx, highlighted ? GColorWhite : GColorBlack);
  text(ctx, r->name, FONT_KEY_GOTHIC_24_BOLD, GRect(6, -2, b.size.w - 74, 28), GTextAlignmentLeft);
  text(ctx, value, FONT_KEY_GOTHIC_24_BOLD, GRect(b.size.w - 72, -2, 66, 28), GTextAlignmentRight);
  graphics_context_set_text_color(ctx, highlighted ? GColorWhite : GColorDarkGray);
  text(ctx, sub, FONT_KEY_GOTHIC_18, GRect(6, 24, b.size.w - 12, 22), GTextAlignmentLeft);
}

static uint16_t get_num_sections(MenuLayer *menu, void *ctx) {
  return g_snow.fav_count ? 3 : 2;
}

static uint16_t get_num_rows(MenuLayer *menu, uint16_t section, void *ctx) {
  if (section == 0) {
    return 1;
  }
  return is_fav_section(section) ? g_snow.fav_count : g_snow.count - g_snow.fav_count;
}

static int16_t get_header_height(MenuLayer *menu, uint16_t section, void *ctx) {
  return (section > 0 && g_snow.fav_count) ? MENU_CELL_BASIC_HEADER_HEIGHT : 0;
}

static void draw_header(GContext *ctx, const Layer *cell, uint16_t section, void *data) {
  menu_cell_basic_header_draw(ctx, cell, is_fav_section(section) ? "Favourites" : "Other resorts");
}

static int16_t get_cell_height(MenuLayer *menu, MenuIndex *index, void *ctx) {
  return index->section == 0 ? HEADER_ROW_H : RESORT_ROW_H;
}

static void draw_row(GContext *ctx, const Layer *cell, MenuIndex *index, void *data) {
  bool highlighted = menu_cell_layer_is_highlighted(cell);
  if (index->section == 0) {
    draw_board_header(ctx, cell, highlighted);
  } else {
    draw_resort(ctx, cell, &g_snow.resorts[g_snow.order[row_pos(index)]], highlighted);
  }
}

static void select_click(MenuLayer *menu, MenuIndex *index, void *ctx) {
  if (index->section == 0) {
    next_board();
  } else {
    s_back_from_detail = true;
    detail_push(row_pos(index));
  }
}

static void select_long_click(MenuLayer *menu, MenuIndex *index, void *ctx) {
  next_board();
}

static void inbox_received(DictionaryIterator *iter, void *ctx) {
  if (cam_handle_message(iter)) {
    return;
  }
  Tuple *blob = dict_find(iter, MESSAGE_KEY_BLOB);
  Tuple *updated = dict_find(iter, MESSAGE_KEY_TIME);
  Tuple *day0 = dict_find(iter, MESSAGE_KEY_DAY0);
  Tuple *status = dict_find(iter, MESSAGE_KEY_STATUS);
  Tuple *board = dict_find(iter, MESSAGE_KEY_DEFAULT_BOARD);
  bool had_data = g_snow.count > 0;
  Board show = g_snow.board;

  if (board && board->value->int32 >= 0 && board->value->int32 < BOARD_COUNT) {
    show = board->value->int32;
    persist_write_int(KEY_BOARD, show);
  }
  if (blob && updated && day0 &&
      snow_set_blob(blob->value->data, blob->length, updated->value->int32, day0->value->int32)) {
    snow_save();
    s_status[0] = '\0';
  }
  if (status) {
    snprintf(s_status, sizeof(s_status), "%s", status->value->cstring);
  }
  snow_sort(show);
  menu_layer_reload_data(s_menu);
  if (!had_data && g_snow.count) {
    menu_layer_set_selected_index(s_menu, MenuIndex(1, 0), MenuRowAlignNone, false);
  }
  detail_refresh();
}

static void inbox_dropped(AppMessageResult reason, void *ctx) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "message dropped: %d", (int)reason);
}

static void tick(struct tm *now, TimeUnits changed) {
  menu_layer_reload_data(s_menu);  // keeps "updated N min ago" current
}

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  s_menu = menu_layer_create(layer_get_bounds(root));
  menu_layer_set_callbacks(s_menu, NULL, (MenuLayerCallbacks) {
    .get_num_sections = get_num_sections,
    .get_num_rows = get_num_rows,
    .get_header_height = get_header_height,
    .draw_header = draw_header,
    .get_cell_height = get_cell_height,
    .draw_row = draw_row,
    .select_click = select_click,
    .select_long_click = select_long_click,
  });
  menu_layer_set_normal_colors(s_menu, GColorWhite, GColorBlack);
  menu_layer_set_highlight_colors(s_menu, GColorCobaltBlue, GColorWhite);
  menu_layer_set_click_config_onto_window(s_menu, window);
  if (g_snow.count) {
    menu_layer_set_selected_index(s_menu, MenuIndex(1, 0), MenuRowAlignNone, false);
  }
  layer_add_child(root, menu_layer_get_layer(s_menu));
}

static void window_appear(Window *window) {
  if (s_back_from_detail && detail_pos() < g_snow.count) {
    menu_layer_set_selected_index(s_menu, pos_index(detail_pos()), MenuRowAlignCenter, false);
  }
  s_back_from_detail = false;
}

static void window_unload(Window *window) {
  menu_layer_destroy(s_menu);
}

static void init(void) {
  snow_load();
  Board board = persist_exists(KEY_BOARD) ? (Board)persist_read_int(KEY_BOARD) : BOARD_NEXT72;
  snow_sort(board < BOARD_COUNT ? board : BOARD_NEXT72);

  s_window = window_create();
  window_set_window_handlers(s_window, (WindowHandlers) {
    .load = window_load,
    .appear = window_appear,
    .unload = window_unload,
  });
  window_stack_push(s_window, true);

  app_message_register_inbox_received(inbox_received);
  app_message_register_inbox_dropped(inbox_dropped);
  app_message_open(MAX_RESORTS * REC_SIZE + 256, 64);
  tick_timer_service_subscribe(MINUTE_UNIT, tick);
}

static void deinit(void) {
  tick_timer_service_unsubscribe();
  cam_deinit();
  detail_deinit();
  window_destroy(s_window);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
