"""身份全成员审核后，仅用当前选定证据生成并复核新摘要。"""

from src.models.news import News
from src.llm import LLMClient
from src.services.event_preparation import PreparedEvent, prepare_events
from src.services.event_quality import select_evidence
from src.services.story_review import StoryReview, membership_hash


async def prepare_story_brief(
    llm: LLMClient, members: list[News], review: StoryReview
) -> PreparedEvent | None:
    if not review.accepted:
        return None
    selected = select_evidence(members)
    prepared, _ = await prepare_events(
        selected, [[1.0, 0.0] for _ in selected], llm, {}, max_calls=2,
        candidate_groups=[selected], identity_reviewed=True,
    )
    if len(prepared) != 1 or prepared[0].provenance.get('mode') != 'ai_joint_verified':
        return None
    item = prepared[0]
    item.news = members
    item.provenance.update(identity_review=review.model_dump(), membership_hash=membership_hash(members),
                           current_support_ids=[n.id for n in selected])
    return item
