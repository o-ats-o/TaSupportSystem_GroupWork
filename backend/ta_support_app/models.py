from django.db import models

# Create your models here.

class Data(models.Model):
    group_id = models.CharField(max_length=10)
    transcript = models.TextField()
    transcript_diarize = models.TextField()
    utterance_count = models.IntegerField()
    sentiment_value = models.FloatField()

    def __str__(self):
        return f"{self.group_id}"