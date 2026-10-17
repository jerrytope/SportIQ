from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("live", "0001_initial")]

    operations = [
        # Questions asked before moderation existed were already public, so they start approved.
        migrations.AddField(model_name="sessionquestion", name="is_approved", field=models.BooleanField(default=True)),
        migrations.AlterField(
            model_name="sessionquestion",
            name="is_approved",
            field=models.BooleanField(default=False, help_text="Shown to attendees only after the host approves it"),
        ),
    ]
