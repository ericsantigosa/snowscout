#pragma once

// Resort detail: 7-day snowfall bars and the numbers behind the boards.
// `pos` is a position in g_snow.order; Up/Down step through the current board.
void detail_push(int pos);
void detail_refresh(void);  // call after g_snow changed
int detail_pos(void);
void detail_deinit(void);
