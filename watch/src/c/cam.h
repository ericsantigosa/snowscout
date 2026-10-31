#pragma once
#include <pebble.h>

// Webcam still for one resort, fetched and converted by the phone (src/pkjs/cam.js) and
// received in chunks. `index` is the resort's position in g_snow.resorts.
void cam_push(int index, const char *name);
bool cam_handle_message(DictionaryIterator *iter);  // true when the message was for the webcam
void cam_deinit(void);
