"""Projection checks and the explicit boundary to Horizons' coordinate contract."""

import math

from .errors import DatasetError


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def circular_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


class CoordinateAdapter:
    def __init__(self, reference):
        from pyproj import CRS, Transformer

        self.reference = reference
        self.crs = CRS.from_wkt(reference.crs_wkt)
        a, b = self.crs.ellipsoid.semi_major_metre, self.crs.ellipsoid.semi_minor_metre
        if not self.crs.is_projected or not all(
            abs(axis.unit_conversion_factor - 1) < 1e-12 for axis in self.crs.axis_info
        ):
            raise DatasetError("INVALID_CRS", "A lunar projected CRS in metres is required")
        if not (abs(a - reference.radius_m) < 1e-6 and abs(b - a) < 1e-6):
            raise DatasetError(
                "INVALID_CRS", "This adapter supports declared lunar spherical coordinates only"
            )
        if not 1700000 < a < 1800000:
            raise DatasetError("INVALID_CRS", "Reference sphere is not lunar")
        self.inverse = Transformer.from_crs(self.crs, self.crs.geodetic_crs, always_xy=True)
        self.forward = Transformer.from_crs(self.crs.geodetic_crs, self.crs, always_xy=True)

    def validate(self, latitude, longitude, x, y):
        if not all(finite(v) for v in (latitude, longitude, x, y)):
            raise DatasetError("INVALID_COORDINATES", "Cell center coordinates must be finite")
        low, high = (
            (-180, 180) if self.reference.longitude_convention == "east_signed" else (0, 360)
        )
        if not -90 <= latitude <= 90 or not low <= longitude < high:
            raise DatasetError(
                "INVALID_COORDINATES", "Source latitude/longitude violates its declared convention"
            )
        lon_check, lat_check = self.inverse.transform(x, y, errcheck=True)
        if abs(latitude - lat_check) > 1e-8 or circular_difference(longitude, lon_check) > 1e-8:
            raise DatasetError(
                "COORDINATE_MISMATCH",
                "Geographic center does not match the source projected center",
            )
        px, py = self.forward.transform(longitude, latitude, errcheck=True)
        error = math.hypot(px - x, py - y)
        if error > 0.001:
            raise DatasetError(
                "COORDINATE_MISMATCH", "Projection round trip exceeds 1 mm numerical tolerance"
            )
        return error

    def to_horizons(self, latitude, longitude):
        # No ME/PA transformation is guessed. Source frames are checked by the schema.
        # On this verified sphere, planetocentric and planetodetic latitude coincide.
        if abs(self.reference.radius_m - 1737400) > 1e-6:
            raise DatasetError(
                "HORIZONS_REFERENCE_MISMATCH",
                "Reference-sphere compatibility needs scientific review",
            )
        return latitude, longitude % 360
