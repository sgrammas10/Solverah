# ============================================================================
# Person-side culture assessment (S-01)
#
# The two routes below are thin on purpose. Every correctness requirement -- the
# server-authoritative shuffle (D-04), the cross-dimension interleave, the opaque item
# tokens, the per-dimension arity check (D-02) -- lives in assessment_form.py and
# present_items.py. A route that reimplements any of it, or reaches past
# assessment_form into present_items / score_person_side directly, is a bug.
# ============================================================================


@app.get("/api/assessment/form")
@jwt_required()
def assessment_form_get():
    """GET /api/assessment/form — the person-side items, ordered for this respondent.

    The payload carries `blocks`, not `dimensions`. The client renders it verbatim: it must
    not sort, group, re-shuffle, or reorder options. Ordering is server-authoritative
    because two independent PRNGs in two languages diverging is silent, and a divergence
    corrupts a resumed session's ordering rather than raising.

    Returns:
        200 {"form_version": str, "respondent_id": str, "blocks": [...]}
        401 if unauthenticated
        404 if user not found
        500 if the item file or its presentation contract is unservable
    """
    from assessment_form import PresentationContractError, get_form
    from assessment_store import respondent_id_for_user

    user = User.query.filter_by(email=get_jwt_identity()).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        payload = get_form(respondent_id_for_user(user.id))
    except PresentationContractError as exc:
        # Do not degrade to an unshuffled form. A form that silently renders in difficulty
        # order produces data that looks fine and is not (D-07).
        app.logger.error("assessment form unservable: %s", exc)
        return jsonify({"error": "Assessment is temporarily unavailable"}), 500

    return jsonify(payload), 200


@limiter.limit("5 per minute")
@app.post("/api/assessment/submit")
@jwt_required()
def assessment_submit():
    """POST /api/assessment/submit — score and persist a completed assessment.

    Body (JSON):
        responses (object): exactly 24 entries of {item_token: option_key}.

    Returns:
        200 {"submission_id": str, "scoring_key_version": str, "dimensions_scored": int}
        400 if the response set is incomplete, padded, or contains an unknown token/option
        401 if unauthenticated
        404 if user not found

    The six dimension scores are NOT returned. The documented threat to this instrument is
    aspirational answering by a user self-profiling for matching, and handing back the six
    numbers gives a retaking respondent a gradient to optimise against -- it teaches the
    item-to-dimension mapping that the shuffle and the interleave exist to hide. Whatever the
    user is eventually shown about their own profile should be designed against that
    pressure, not fall out of the submit response by default.
    """
    from assessment_form import AssessmentError, submit_form
    from assessment_store import persist_submission, respondent_id_for_user

    data = request.get_json(silent=True) or {}
    responses = data.get("responses")

    user = User.query.filter_by(email=get_jwt_identity()).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        result = submit_form(respondent_id_for_user(user.id), responses)
    except AssessmentError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        submission_id = persist_submission(db, user.id, result)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({
        "submission_id": submission_id,
        "scoring_key_version": result.scoring_key_version,
        "dimensions_scored": len(result.scores),
    }), 200
