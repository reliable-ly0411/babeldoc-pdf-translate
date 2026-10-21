"""Explicit test doubles. These are never imported by production scripts."""
import audit_receipts as durable


def reviewer(verdict='equivalent', raw=None, seen=None):
    def inspect(packet, budget, folder):
        if seen is not None:
            seen.append(packet)
        response = raw if raw is not None else durable.encode({
            'verdict': verdict,
            'source_meaning': 'Offline fixture asserts a controlled statement.',
            'target_meaning': 'Offline fixture asserts the same controlled statement.',
            'note': 'Synthetic response; no real semantic or model validation.'})
        return budget.invoke('offline-semantic', lambda timeout: (response, {'input_tokens': 1, 'output_tokens': 1}))
    inspect.model = 'offline-semantic'
    inspect.backend = 'offline'
    return inspect


def adjudicate(inbox, binding, unit, response, budget):
    """Trusted fake for mechanics only; cannot establish real factual support."""
    if not (inbox / 'decision.ready').exists():
        durable.publish(inbox / 'decision.ready', durable.encode({
            'receipt_version': durable.VERSION, 'binding': binding, 'decision': 'pass',
            'review': {'source_meaning_supported': True, 'target_meaning_supported': True,
                       'difference_supported': True,
                       'evidence': 'Explicit OFFLINE TEST fixture adjudication, never a factual production signature.'}}))


def options(**kwargs):
    return {'semantic_auditor': reviewer(**kwargs), 'semantic_adjudicator': adjudicate}
