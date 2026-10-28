"""Point-in-time resolver tests: the alignment rule is the most leakage-sensitive step of the news pipeline."""
import pandas as pd

from app.features.news_pit import is_low_precision, resolve_effective_dates

CAL = pd.DatetimeIndex(pd.bdate_range("2023-06-26", "2023-07-14")).difference(
    pd.DatetimeIndex(["2023-07-04"]))  # US market holiday


def eff(ts_str, cal=CAL):
    s = pd.Series([pd.Timestamp(ts_str, tz="UTC")])
    return resolve_effective_dates(s, cal).iloc[0]


def et(local_str):
    """UTC timestamp string for a New York wall-clock time."""
    return pd.Timestamp(local_str, tz="America/New_York").tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")


def test_friday_after_close_maps_to_monday():
    r = eff(et("2023-06-30 16:01:05"))          # Friday 16:01:05 ET
    assert r.effective_date == pd.Timestamp("2023-07-03")      # Monday


def test_before_close_maps_to_same_day():
    assert eff(et("2023-06-30 15:59:30")).effective_date == pd.Timestamp("2023-06-30")


def test_at_or_after_close_maps_to_next_session():
    assert eff(et("2023-06-29 16:00:30")).effective_date == pd.Timestamp("2023-06-30")
    # 16:00:00 sharp is also low-precision and is likewise pushed to the next session
    assert eff(et("2023-06-29 16:00:00")).effective_date == pd.Timestamp("2023-06-30")


def test_weekend_maps_to_next_trading_day():
    assert eff(et("2023-07-01 11:15:20")).effective_date == pd.Timestamp("2023-07-03")   # Saturday


def test_holiday_maps_to_next_trading_day():
    assert eff(et("2023-07-04 10:12:31")).effective_date == pd.Timestamp("2023-07-05")   # Independence Day
    assert eff(et("2023-07-03 17:30:10")).effective_date == pd.Timestamp("2023-07-05")   # eve of holiday, after close


def test_dst_is_handled_via_new_york_timezone():
    # 20:30:10 UTC is 16:30 ET in July (EDT) but 15:30 ET in January (EST)
    cal = pd.DatetimeIndex(pd.bdate_range("2023-01-02", "2023-07-31"))
    assert eff("2023-07-12 20:30:10", cal).effective_date == pd.Timestamp("2023-07-13")
    assert eff("2023-01-12 20:30:10", cal).effective_date == pd.Timestamp("2023-01-12")


def test_date_only_stamp_is_next_trading_day():
    r = eff("2023-06-28 00:00:00")               # midnight UTC = date-only
    assert r.low_precision and r.effective_date == pd.Timestamp("2023-06-29")
    assert eff("2023-06-30 00:00:00").effective_date == pd.Timestamp("2023-07-03")   # Friday -> Monday


def test_low_precision_detection():
    s = pd.Series(pd.to_datetime(["2023-06-28 00:00:00", "2023-06-28 14:00:00", "2023-06-28 14:00:01",
                                  "2023-06-28 14:05:00"], utc=True))
    assert is_low_precision(s).tolist() == [True, True, False, False]


def test_never_earlier_than_publication_session():
    ts = pd.Series(pd.date_range("2023-06-26 00:00:07", "2023-07-12 23:59:59", freq="3h17min", tz="UTC"))
    out = resolve_effective_dates(ts, CAL)
    pub_et_date = ts.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    ok = out["effective_date"].notna()
    assert (out.loc[ok, "effective_date"] >= pub_et_date[ok]).all()
    assert out.loc[ok, "effective_date"].isin(CAL).all()


def test_beyond_calendar_is_nat():
    assert pd.isna(eff("2023-07-14 21:00:07").effective_date)
