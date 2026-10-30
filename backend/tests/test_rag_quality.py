import pytest
from app.models.contracts import Question,Claim,Draft,Verification
from app.services import retrieval,answering,llm,citations,versioning
from app.core.database import connection
from test_rag import store,policies,add,mock_answer


def test_equivalent_queries_select_same_current_passages(policies):
    a,_=retrieval.retrieve(Question(question='How many medical leaves are allowed in 2026?'))
    b,_=retrieval.retrieve(Question(question='medical leaves'))
    assert [c.chunk_id for c in a]==[c.chunk_id for c in b]
    assert a and all(c.version=='2026' for c in a)


def test_comparison_retains_both_versions(policies):
    chunks,_=retrieval.retrieve(Question(question='Compare the 2024 and 2026 medical leave policies.'))
    assert {c.version for c in chunks}=={'2024','2026'}


def test_irrelevant_diagnostics_do_not_downgrade_verified_answer(policies,monkeypatch):
    chunks,_=retrieval.retrieve(Question(question='medical leave'))
    monkeypatch.setattr(retrieval,'retrieve',lambda *a:(chunks,['Keyword retrieval unavailable; semantic fallback used','No effective current document in unrelated-family']))
    mock_answer(monkeypatch)
    result=answering.ask(Question(question='medical leave'))
    assert result.status=='answered' and not result.warnings


def test_rejected_extra_claim_does_not_override_verified_coverage(policies,monkeypatch):
    def generate(schema,instruction,payload):
        c=payload['evidence'][0]
        if schema is Draft:
            return Draft(claims=[Claim(text='Employees receive 12 days of medical leave per year.',chunk_id=c['chunk_id'],quote=c['text']),Claim(text='Unsupported extra.',chunk_id='invented',quote='invented')])
        assert len(payload['claims'])==1
        return Verification(supported_claims=[0],supported_parts=['Medical leave allowance'],unsupported_parts=[],all_parts_covered=True)
    monkeypatch.setattr(llm,'generate',generate)
    assert answering.ask(Question(question='medical leave')).status=='answered'


def test_year_metadata_is_valid_but_quantity_must_be_in_quote(policies):
    chunks,_=retrieval.retrieve(Question(question='medical leave'))
    c=chunks[0]
    valid=Claim(text='In 2026 employees receive 12 days of medical leave.',chunk_id=c.chunk_id,quote=c.text)
    wrong=valid.model_copy(update={'text':'In 2026 employees receive 120 days.'})
    empty=valid.model_copy(update={'quote':'   '})
    year_as_quantity=valid.model_copy(update={'text':'Employees receive 2026 medical leave days.'})
    claims,refs=citations.validate_claims([valid,wrong,empty,year_as_quantity],chunks)
    assert claims==[valid] and len(refs)==1


def test_unknown_or_mismatched_source_cannot_validate(policies):
    chunks,_=retrieval.retrieve(Question(question='medical leave'))
    c=chunks[0];claim=Claim(text='12 days.',chunk_id=c.chunk_id,quote=c.text)
    assert citations.validate_claims([claim],[c.model_copy(update={'document_id':'other'})])==([],[])
    assert citations.validate_claims([claim],chunks,'tcs')==([],[])


def test_conflicting_versions_are_excluded_without_leaking_diagnostics(policies):
    add('Medical leave allowance is 14 days.','2025','current')
    result=answering.ask(Question(question='current medical leave'))
    assert result.status=='not_covered'
    assert 'Conflicting policy versions' in result.warnings[0]
    assert 'Ambiguous authority in leave' not in str(result)


def test_control_blocks_not_employee_evidence():
    assert retrieval.is_control_block('Policy ID: X\nVersion: 2026\nStatus: current')
    assert not retrieval.is_control_block('Employees must use multifactor authentication.')
