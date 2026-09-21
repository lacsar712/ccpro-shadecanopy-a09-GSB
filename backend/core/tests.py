from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Greenhouse, PalletLine, ShipmentPallet, Zone

User = get_user_model()


class PalletFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.client.force_authenticate(self.user)
        self.g1 = Greenhouse.objects.create(name="一号棚")
        self.g2 = Greenhouse.objects.create(name="二号棚")
        self.z1 = Zone.objects.create(greenhouse=self.g1, zone_code="A-01")
        self.z2 = Zone.objects.create(greenhouse=self.g1, zone_code="A-02")
        self.z3 = Zone.objects.create(greenhouse=self.g2, zone_code="B-01")

    def make_pallet(self, greenhouse, pallet_no="TP-001"):
        return ShipmentPallet.objects.create(
            greenhouse=greenhouse, pallet_no=pallet_no, packed_at=timezone.now()
        )

    def add_line(self, pallet, zone, kg, grade="甲"):
        return self.client.post(
            "/api/pallet-lines/",
            {"palletId": pallet.id, "zoneId": zone.id, "kg": str(kg), "grade": grade},
            format="json",
        )

    def test_ship_requires_two_lines(self):
        pallet = self.make_pallet(self.g1)
        self.add_line(pallet, self.z1, "6.000")
        resp = self.client.post(f"/api/pallets/{pallet.id}/ship/")
        self.assertEqual(resp.status_code, 409)
        pallet.refresh_from_db()
        self.assertIsNone(pallet.shipped_at)

    def test_ship_requires_total_over_5(self):
        pallet = self.make_pallet(self.g1)
        self.add_line(pallet, self.z1, "2.500")
        self.add_line(pallet, self.z2, "2.500")
        resp = self.client.post(f"/api/pallets/{pallet.id}/ship/")
        self.assertEqual(resp.status_code, 409)
        pallet.refresh_from_db()
        self.assertIsNone(pallet.shipped_at)

    def test_ship_success_then_loading_forbidden(self):
        pallet = self.make_pallet(self.g1)
        self.add_line(pallet, self.z1, "3.250")
        self.add_line(pallet, self.z2, "2.750")
        resp = self.client.post(f"/api/pallets/{pallet.id}/ship/")
        self.assertEqual(resp.status_code, 200)
        pallet.refresh_from_db()
        self.assertIsNotNone(pallet.shipped_at)
        # 发运后禁止再装入
        resp = self.add_line(pallet, self.z1, "1.000")
        self.assertEqual(resp.status_code, 409)
        # 重复发运也冲突
        resp = self.client.post(f"/api/pallets/{pallet.id}/ship/")
        self.assertEqual(resp.status_code, 409)

    def test_line_zone_must_belong_to_pallet_greenhouse(self):
        pallet = self.make_pallet(self.g1)
        resp = self.add_line(pallet, self.z3, "1.000")
        self.assertEqual(resp.status_code, 400)

    def test_grade_choices(self):
        pallet = self.make_pallet(self.g1)
        resp = self.add_line(pallet, self.z1, "1.000", grade="丙")
        self.assertEqual(resp.status_code, 400)
        resp = self.add_line(pallet, self.z1, "1.000", grade="乙")
        self.assertEqual(resp.status_code, 201)

    def test_pallet_no_unique_per_greenhouse_only(self):
        self.make_pallet(self.g1, "TP-001")
        # 同温室撞号 -> 400
        resp = self.client.post(
            "/api/pallets/",
            {
                "greenhouseId": self.g1.id,
                "palletNo": "TP-001",
                "packedAt": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # 跨温室同号 -> 允许
        resp = self.client.post(
            "/api/pallets/",
            {
                "greenhouseId": self.g2.id,
                "palletNo": "TP-001",
                "packedAt": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_cross_greenhouse_same_pallet_no_not_mixed(self):
        p1 = self.make_pallet(self.g1, "TP-001")
        p2 = self.make_pallet(self.g2, "TP-001")
        self.add_line(p1, self.z1, "3.000")
        self.add_line(p2, self.z3, "7.000")
        resp = self.client.get("/api/pallets/", {"greenhouseId": self.g1.id})
        rows = resp.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["palletNo"], "TP-001")
        self.assertEqual(Decimal(rows[0]["totalKg"]), Decimal("3.000"))
        resp = self.client.get("/api/pallets/", {"greenhouseId": self.g2.id})
        rows = resp.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(rows[0]["totalKg"]), Decimal("7.000"))

    def test_summary_matches_detail_lines(self):
        p1 = self.make_pallet(self.g1, "TP-001")
        p2 = self.make_pallet(self.g1, "TP-002")
        p3 = self.make_pallet(self.g2, "TP-001")
        self.add_line(p1, self.z1, "1.234")
        self.add_line(p1, self.z2, "2.345")
        self.add_line(p2, self.z1, "3.456")
        self.add_line(p3, self.z3, "9.876")

        resp = self.client.get("/api/pallets/summary/")
        self.assertEqual(resp.status_code, 200)
        summary = {row["greenhouseId"]: row for row in resp.data}
        self.assertEqual(summary[self.g1.id]["palletCount"], 2)
        self.assertEqual(summary[self.g2.id]["palletCount"], 1)

        for greenhouse in (self.g1, self.g2):
            detail_total = sum(
                (line.kg for line in PalletLine.objects.filter(pallet__greenhouse=greenhouse)),
                Decimal("0"),
            )
            diff = abs(Decimal(summary[greenhouse.id]["totalKg"]) - detail_total)
            self.assertLessEqual(diff, Decimal("0.001"))
