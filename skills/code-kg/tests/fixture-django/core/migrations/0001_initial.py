"""Initial schema."""
import django.contrib.auth.models
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Org",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("username", models.CharField(max_length=150, unique=True)),
                ("org", models.ForeignKey(on_delete=models.CASCADE, related_name="members", to="core.org")),
            ],
            bases=(models.Model,),
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
    ]
