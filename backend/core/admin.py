from django.contrib import admin

from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    PalletLine,
    ShipmentPallet,
    Zone,
)


@admin.register(Greenhouse)
class GreenhouseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "location", "area_m2")
    search_fields = ("name", "location")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("id", "greenhouse", "zone_code", "crop_name", "status")
    list_filter = ("status", "greenhouse")
    search_fields = ("zone_code", "crop_name")


@admin.register(ClimateLog)
class ClimateLogAdmin(admin.ModelAdmin):
    list_display = ("id", "zone", "recorded_at", "temp_c", "humidity_pct", "par_umol", "co2_ppm")
    list_filter = ("zone",)


@admin.register(IrrigationCycle)
class IrrigationCycleAdmin(admin.ModelAdmin):
    list_display = ("id", "zone", "start_at", "duration_min", "water_liters", "status")
    list_filter = ("status", "zone")


class PalletLineInline(admin.TabularInline):
    model = PalletLine
    extra = 0


@admin.register(ShipmentPallet)
class ShipmentPalletAdmin(admin.ModelAdmin):
    list_display = ("id", "greenhouse", "pallet_no", "packed_at", "shipped_at")
    list_filter = ("greenhouse",)
    search_fields = ("pallet_no",)
    inlines = [PalletLineInline]


@admin.register(PalletLine)
class PalletLineAdmin(admin.ModelAdmin):
    list_display = ("id", "pallet", "zone", "kg", "grade")
    list_filter = ("grade", "pallet__greenhouse")
