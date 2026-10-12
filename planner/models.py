from django.db import models


class FuelStation(models.Model):
    opis_id = models.CharField(max_length=32, blank=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=9, decimal_places=5, help_text="USD per gallon")
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
