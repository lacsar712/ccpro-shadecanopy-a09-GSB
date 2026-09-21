from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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


class ShipmentPalletViewSet(viewsets.ModelViewSet):
    serializer_class = ShipmentPalletSerializer

    def get_queryset(self):
        qs = (
            ShipmentPallet.objects.select_related("greenhouse")
            .annotate(
                line_count=Count("lines"),
                total_kg=Coalesce(Sum("lines__kg"), Decimal("0.000")),
            )
            .order_by("greenhouse_id", "pallet_no")
        )
        greenhouse_id = self.request.query_params.get("greenhouseId")
        shipped = self.request.query_params.get("shipped")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if shipped == "true":
            qs = qs.filter(shipped_at__isnull=False)
        elif shipped == "false":
            qs = qs.filter(shipped_at__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        pallet = self.get_object()
        if pallet.is_shipped:
            return Response(
                {"detail": "托盘已发运，请勿重复发运"},
                status=status.HTTP_409_CONFLICT,
            )
        agg = pallet.lines.aggregate(
            line_count=Count("id"),
            total_kg=Coalesce(Sum("kg"), Decimal("0.000")),
        )
        if agg["line_count"] < 2 or agg["total_kg"] <= Decimal("5"):
            return Response(
                {
                    "detail": "托盘至少两行且公斤合计大于 5 才能发运",
                    "lineCount": agg["line_count"],
                    "totalKg": agg["total_kg"],
                },
                status=status.HTTP_409_CONFLICT,
            )
        pallet.shipped_at = timezone.now()
        pallet.save(update_fields=["shipped_at", "updated_at"])
        pallet.line_count = agg["line_count"]
        pallet.total_kg = agg["total_kg"]
        return Response(self.get_serializer(pallet).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        rows = (
            Greenhouse.objects.annotate(
                pallet_count=Count("shipment_pallets", distinct=True),
                total_kg=Coalesce(
                    Sum("shipment_pallets__lines__kg"), Decimal("0.000")
                ),
            )
            .order_by("id")
        )
        data = [
            {
                "greenhouseId": g.id,
                "greenhouseName": g.name,
                "palletCount": g.pallet_count,
                "totalKg": float(g.total_kg),
            }
            for g in rows
        ]
        return Response(data)


class PalletLineViewSet(viewsets.ModelViewSet):
    serializer_class = PalletLineSerializer

    def get_queryset(self):
        qs = PalletLine.objects.select_related(
            "pallet", "pallet__greenhouse", "zone"
        ).all()
        pallet_id = self.request.query_params.get("palletId")
        greenhouse_id = self.request.query_params.get("greenhouseId")
        if pallet_id:
            qs = qs.filter(pallet_id=pallet_id)
        if greenhouse_id:
            qs = qs.filter(pallet__greenhouse_id=greenhouse_id)
        return qs


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
