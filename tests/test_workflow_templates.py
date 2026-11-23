from legal_bot.workflow_templates import list_workflow_templates


def test_workflow_catalog_has_curated_multistep_paths_and_existing_actions():
    items = list_workflow_templates()
    assert {x['id'] for x in items} >= {'new-case-review', 'contract-review', 'draft-preparation'}
    allowed = {'workspace', 'documents', 'review', 'ai', 'drafting'}
    for item in items:
        assert 2 <= len(item['steps']) <= 8
        assert all(step['action'] in allowed for step in item['steps'])
        assert all(step.get('title') and step.get('instruction') for step in item['steps'])


def test_workflow_catalog_is_defensively_copied():
    first = list_workflow_templates()
    first[0]['title'] = 'changed'
    assert list_workflow_templates()[0]['title'] != 'changed'


def test_ai_workflow_steps_have_reviewable_prompts():
    for item in list_workflow_templates():
        for step in item['steps']:
            if step['action'] == 'ai':
                assert len(step.get('prompt', '')) > 80
                assert 'حدس' in step['prompt'] or 'نساز' in step['prompt'] or 'فرض' in step['prompt']


def test_authenticated_api_exposes_workflow_catalog_route():
    import inspect
    from legal_bot.api import APIHandler
    source = inspect.getsource(APIHandler.do_GET)
    assert '/workflow-templates' in source
    assert 'list_workflow_templates()' in source
