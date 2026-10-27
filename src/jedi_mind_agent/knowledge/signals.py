from django.db.models.signals import post_delete
from django.dispatch import receiver

from jedi_mind_agent.knowledge.models import Book


@receiver(post_delete, sender=Book)
def delete_book_file(sender, instance: Book, **kwargs) -> None:
    # The chunks go with the row (ON DELETE CASCADE); the PDF on the shared volume is removed here.
    if instance.file:
        instance.file.delete(save=False)
