from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .exceptions import Conflict
from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    PalletLine,
    ShipmentPallet,
    Zone,
)
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    PalletLineSerializer,
    ShipmentPalletSerializer,
    ZoneSerializer,
)


class GreenhouseViewSet(viewsets.ModelViewSet):
    queryset = Greenhouse.objects.annotate(zone_count=Count("zones")).all()
    serializer_class = GreenhouseSerializer


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = Zone.objects.select_related("greenhouse").all()
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class ClimateLogViewSet(viewsets.ModelViewSet):
    serializer_class = ClimateLogSerializer

    def get_queryset(self):
        qs = ClimateLog.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class IrrigationCycleViewSet(viewsets.ModelViewSet):
    serializer_class = IrrigationCycleSerializer

    def get_queryset(self):
        qs = IrrigationCycle.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            qs = qs.filter(status=status)
        return qs


def _kg_sum_expression(field):
    return Coalesce(
        Sum(field),
        Value(Decimal("0.000")),
        output_field=DecimalField(max_digits=14, decimal_places=3),
    )


class ShipmentPalletViewSet(viewsets.ModelViewSet):
    serializer_class = ShipmentPalletSerializer

    def get_queryset(self):
        qs = (
            ShipmentPallet.objects.select_related("greenhouse")
            .prefetch_related("lines", "lines__zone")
            .annotate(
                line_count=Count("lines"),
                total_kg=_kg_sum_expression("lines__kg"),
            )
            .order_by("greenhouse_id", "pallet_no")
        )
        greenhouse_id = self.request.query_params.get("greenhouseId")
        shipped = self.request.query_params.get("shipped")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if shipped in ("true", "false"):
            qs = qs.filter(shipped_at__isnull=(shipped == "false"))
        return qs

    def destroy(self, request, *args, **kwargs):
        pallet = self.get_object()
        if pallet.is_shipped:
            raise Conflict("托盘已发运，禁止删除")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        pallet = self.get_object()
        if pallet.is_shipped:
            raise Conflict("托盘已发运")
        line_count = pallet.lines.count()
        total_kg = pallet.lines.aggregate(
            s=_kg_sum_expression("kg")
        )["s"]
        if line_count < 2:
            raise Conflict("发运失败：装盘行不足两行，发运时刻保持空")
        if total_kg <= Decimal("5"):
            raise Conflict("发运失败：公斤合计须大于 5，发运时刻保持空")
        pallet.shipped_at = timezone.now()
        pallet.save(update_fields=["shipped_at", "updated_at"])
        return Response(self.get_serializer(pallet).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        rows = (
            Greenhouse.objects.annotate(
                pallet_count=Count("pallets", distinct=True),
                shipped_count=Count(
                    "pallets",
                    filter=Q(pallets__shipped_at__isnull=False),
                    distinct=True,
                ),
                total_kg=_kg_sum_expression("pallets__lines__kg"),
            )
            .order_by("id")
        )
        data = [
            {
                "greenhouseId": row.id,
                "greenhouseName": row.name,
                "palletCount": row.pallet_count,
                "shippedCount": row.shipped_count,
                "totalKg": str(row.total_kg.quantize(Decimal("0.001"))),
            }
            for row in rows
        ]
        return Response(data)


class PalletLineViewSet(viewsets.ModelViewSet):
    serializer_class = PalletLineSerializer

    def get_queryset(self):
        qs = PalletLine.objects.select_related(
            "pallet", "pallet__greenhouse", "zone"
        ).all()
        pallet_id = self.request.query_params.get("palletId")
        zone_id = self.request.query_params.get("zoneId")
        if pallet_id:
            qs = qs.filter(pallet_id=pallet_id)
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs

    def destroy(self, request, *args, **kwargs):
        line = self.get_object()
        if line.pallet.is_shipped:
            raise Conflict("托盘已发运，禁止移除装盘行")
        return super().destroy(request, *args, **kwargs)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
            start_at__gte=today_start,
            start_at__lt=today_end,
        ).count(),
    }
    return Response(data)
