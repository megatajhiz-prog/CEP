from waterprofiler.winsize import MIN_H, MIN_W, fit_size


def test_small_laptop_screen_gets_a_window_that_fits_and_is_maximised():
    w, h, maxi = fit_size(1366, 728)          # 1366x768 minus the taskbar
    assert w <= 1366 and h <= 728 and maxi


def test_large_screen_keeps_the_default_size_and_is_not_maximised():
    assert fit_size(1920, 1040) == (1180, 760, False)


def test_never_smaller_than_the_minimum():
    w, h, _ = fit_size(500, 400)
    assert (w, h) == (MIN_W, MIN_H)
