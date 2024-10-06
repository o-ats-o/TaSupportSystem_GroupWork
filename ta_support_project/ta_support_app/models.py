from django.db import models

# Create your models here.

class Data(models.Model):
    group_id = models.CharField(max_length=10)
    transcript = models.TextField(null=True)
    transcript_diarize = models.TextField(null=True)
    utterance_count = models.IntegerField()
    sentiment_value = models.FloatField()
    datetime = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.group_id}"