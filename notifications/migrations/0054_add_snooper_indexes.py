from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0053_add_email_to_index'),
    ]

    operations = [
        # Add an index for the post_office_email_id field in notifications_snooper
        migrations.RunSQL(
            sql="""
            CREATE INDEX idx_notifications_snooper_email_id
            ON notifications_snooper (post_office_email_id);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_notifications_snooper_email_id;
            """
        ),
        # Add a compound index for batch_id and post_office_email_id in snooper
        migrations.RunSQL(
            sql="""
            CREATE INDEX idx_notifications_snooper_batch_email
            ON notifications_snooper (batch_id_id, post_office_email_id);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_notifications_snooper_batch_email;
            """
        ),
    ] 