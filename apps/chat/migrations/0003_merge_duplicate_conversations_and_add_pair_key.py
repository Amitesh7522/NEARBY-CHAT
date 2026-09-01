# Generated migration for merging duplicate conversations and adding unique direct_pair_key

from django.db import migrations, models
from collections import defaultdict

def merge_duplicates_and_populate_keys(apps, schema_editor):
    Conversation = apps.get_model('chat', 'Conversation')
    ConversationParticipant = apps.get_model('chat', 'ConversationParticipant')
    Message = apps.get_model('chat', 'Message')
    ConversationRating = apps.get_model('chat', 'ConversationRating')

    # Group all conversations by participant user ID pair
    pair_to_convs = defaultdict(list)

    for conv in Conversation.objects.all():
        participant_user_ids = list(conv.participants.values_list('user_id', flat=True))
        if len(participant_user_ids) == 2:
            u1, u2 = str(participant_user_ids[0]), str(participant_user_ids[1])
            pair_key = f"{min(u1, u2)}_{max(u1, u2)}"
            pair_to_convs[pair_key].append(conv)

    for pair_key, convs in pair_to_convs.items():
        if len(convs) == 1:
            conv = convs[0]
            conv.direct_pair_key = pair_key
            conv.save(update_fields=['direct_pair_key'])
        else:
            # Sort: prioritize most messages, then direct over random, then newest
            def conv_score(c):
                msg_count = c.messages.count()
                type_score = 1 if c.type == 'direct' else 0
                return (msg_count, type_score, c.updated_at)

            sorted_convs = sorted(convs, key=conv_score, reverse=True)
            primary = sorted_convs[0]
            secondary_list = sorted_convs[1:]

            for sec in secondary_list:
                # Move messages from secondary to primary
                Message.objects.filter(conversation=sec).update(conversation=primary)

                # Move ratings to primary if not already present
                for rating in ConversationRating.objects.filter(conversation=sec):
                    if not ConversationRating.objects.filter(
                        conversation=primary,
                        rater=rating.rater,
                        ratee=rating.ratee
                    ).exists():
                        rating.conversation = primary
                        rating.save(update_fields=['conversation'])
                    else:
                        rating.delete()

                # Delete secondary conversation
                sec.delete()

            primary.direct_pair_key = pair_key
            primary.save(update_fields=['direct_pair_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_conversationrating'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='direct_pair_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Deterministic unique key for 1-on-1 conversations: min_id_max_id',
                max_length=120,
                null=True,
            ),
        ),
        migrations.RunPython(
            merge_duplicates_and_populate_keys,
            reverse_code=migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name='conversation',
            name='direct_pair_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Deterministic unique key for 1-on-1 conversations: min_id_max_id',
                max_length=120,
                null=True,
                unique=True,
            ),
        ),
    ]
