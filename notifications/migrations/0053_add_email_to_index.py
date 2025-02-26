from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('post_office', '0011_models_help_text'),  # replace with the latest post_office migration
        ('notifications', '0052_auto_20240520_1538'),  # replace with your last notifications migration
    ]

    operations = [
        # Enable the pg_trgm extension
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql="DROP EXTENSION IF EXISTS pg_trgm;"
        ),
        # Create the GIN index with the appropriate operator class
        migrations.RunSQL(
            sql="""
            CREATE INDEX idx_post_office_email_to 
            ON post_office_email USING gin ("to" gin_trgm_ops);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_post_office_email_to;
            """
        ),
        # Add a btree index which might be more useful for exact matches
        migrations.RunSQL(
            sql="""
            CREATE INDEX idx_post_office_email_to_btree
            ON post_office_email ("to");
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_post_office_email_to_btree;
            """
        ),
    ]