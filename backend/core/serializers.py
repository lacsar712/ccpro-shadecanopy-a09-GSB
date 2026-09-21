from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers

from .models import ClimateLog, Greenhouse, IrrigationCycle, PalletLine, ShipmentPallet, Zone


class GreenhouseSerializer(serializers.ModelSerializer):
    areaM2 = serializers.DecimalField(
        source="area_m2", max_digits=10, decimal_places=2
    )
    zoneCount = serializers.SerializerMethodField()

    class Meta:
        model = Greenhouse
        fields = (
            "id",
            "name",
            "location",
            "areaM2",
            "notes",
            "zoneCount",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "zoneCount", "created_at", "updated_at")

    def get_zoneCount(self, obj):
        if hasattr(obj, "zone_count"):
            return obj.zone_count
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    zoneCode = serializers.CharField(source="zone_code")
    cropName = serializers.CharField(source="crop_name", allow_blank=True, required=False)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)

    class Meta:
        model = Zone
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "zoneCode",
            "cropName",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "greenhouseName", "created_at", "updated_at")

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        zone_code = attrs.get("zone_code") or getattr(self.instance, "zone_code", None)
        if greenhouse and zone_code:
            qs = Zone.objects.filter(greenhouse=greenhouse, zone_code=zone_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"zoneCode": "同一温室内分区编码必须唯一"}
                )
        return attrs


class ClimateLogSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    recordedAt = serializers.DateTimeField(source="recorded_at")
    tempC = serializers.DecimalField(source="temp_c", max_digits=5, decimal_places=2)
    humidityPct = serializers.DecimalField(
        source="humidity_pct", max_digits=5, decimal_places=2
    )
    parUmol = serializers.DecimalField(
        source="par_umol", max_digits=8, decimal_places=2, required=False
    )
    co2Ppm = serializers.DecimalField(
        source="co2_ppm", max_digits=8, decimal_places=2, required=False
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = ClimateLog
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "recordedAt",
            "tempC",
            "humidityPct",
            "parUmol",
            "co2Ppm",
            "created_at",
        )
        read_only_fields = ("id", "zoneCode", "greenhouseName", "created_at")

    def validate_humidityPct(self, value):
        if value < 20 or value > 100:
            raise serializers.ValidationError("湿度须在 20～100 之间")
        return value


class IrrigationCycleSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    startAt = serializers.DateTimeField(source="start_at")
    durationMin = serializers.IntegerField(source="duration_min")
    waterLiters = serializers.DecimalField(
        source="water_liters", max_digits=10, decimal_places=2
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = IrrigationCycle
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "startAt",
            "durationMin",
            "waterLiters",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "created_at",
            "updated_at",
        )


class ShipmentPalletSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    palletNo = serializers.CharField(source="pallet_no")
    packedAt = serializers.DateTimeField(source="packed_at")
    shippedAt = serializers.DateTimeField(source="shipped_at", read_only=True)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)
    lineCount = serializers.SerializerMethodField()
    totalKg = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentPallet
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "palletNo",
            "packedAt",
            "shippedAt",
            "lineCount",
            "totalKg",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "greenhouseName",
            "shippedAt",
            "lineCount",
            "totalKg",
            "created_at",
            "updated_at",
        )

    def get_lineCount(self, obj):
        if hasattr(obj, "line_count"):
            return obj.line_count
        return obj.lines.count()

    def get_totalKg(self, obj):
        if hasattr(obj, "total_kg"):
            return obj.total_kg
        return obj.lines.aggregate(
            total=Coalesce(Sum("kg"), Decimal("0.000"))
        )["total"]

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        pallet_no = attrs.get("pallet_no") or getattr(self.instance, "pallet_no", None)
        if greenhouse and pallet_no:
            qs = ShipmentPallet.objects.filter(
                greenhouse=greenhouse, pallet_no=pallet_no
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"palletNo": "同一温室内托盘号必须唯一"}
                )
        if self.instance and self.instance.is_shipped:
            raise serializers.ValidationError("托盘已发运，禁止修改")
        return attrs


class PalletLineSerializer(serializers.ModelSerializer):
    palletId = serializers.PrimaryKeyRelatedField(
        source="pallet", queryset=ShipmentPallet.objects.all()
    )
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    palletNo = serializers.CharField(source="pallet.pallet_no", read_only=True)
    greenhouseName = serializers.CharField(
        source="pallet.greenhouse.name", read_only=True
    )

    class Meta:
        model = PalletLine
        fields = (
            "id",
            "palletId",
            "palletNo",
            "greenhouseName",
            "zoneId",
            "zoneCode",
            "kg",
            "grade",
            "created_at",
        )
        read_only_fields = (
            "id",
            "palletNo",
            "greenhouseName",
            "zoneCode",
            "created_at",
        )

    def validate_kg(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("公斤数必须大于 0")
        return value

    def validate(self, attrs):
        pallet = attrs.get("pallet") or getattr(self.instance, "pallet", None)
        zone = attrs.get("zone") or getattr(self.instance, "zone", None)
        if self.instance and self.instance.pallet.is_shipped:
            raise serializers.ValidationError("托盘已发运，禁止再装入或改行")
        if pallet and pallet.is_shipped:
            raise serializers.ValidationError(
                {"palletId": "托盘已发运，禁止再装入"}
            )
        if pallet and zone and zone.greenhouse_id != pallet.greenhouse_id:
            raise serializers.ValidationError(
                {"zoneId": "分区必须属于托盘所在温室"}
            )
        return attrs
