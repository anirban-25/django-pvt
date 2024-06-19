from rest_framework import serializers


def should_have_value(value):
    if not value:
        raise serializers.ValidationError("Should not be null or empty.")


def should_have_positive_value(value):
    if not value:
        raise serializers.ValidationError("Should not be null or 0.")
    elif float(value) <= 0:
        raise serializers.ValidationError("Should be positive value.")
