# Chat Rating Feature Backup & Reference

This document preserves the complete implementation of the Post-Conversation Rating system so it can easily be re-enabled in the future.

---

## 1. UI Components

### Rate Conversation Banner (`templates/accounts/profile.html`)
```html
{% if can_rate %}
  <div id="rate-conversation-banner" style="margin-bottom: var(--space-5); padding: var(--space-3) var(--space-4); background: var(--bg-subtle); border-radius: var(--radius-lg); border: 1px dashed var(--border-color); display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); text-align: left;">
    <div>
      <div style="font-weight: 700; font-size: var(--text-sm); display: flex; align-items: center; gap: 6px; color: var(--text-primary);">
        <span>⭐</span> {% trans "Rate your conversation" %}
      </div>
      <div style="font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px;">
        {% trans "How was your recent chat with" %} {{ profile.get_display_name }}?
      </div>
    </div>
    <button type="button" onclick="openRatingModal()" class="btn btn-sm btn-primary" style="flex-shrink: 0;">
      {% trans "Rate" %}
    </button>
  </div>
{% endif %}
```

### Rating Modal Inclusion (`templates/accounts/profile.html`)
```html
{% if can_rate %}
  {% include 'includes/rating_modal.html' %}
{% endif %}
```

### Public Rating Badges on Profile (`templates/accounts/profile.html`)
```html
{% if rating_summary.show_public %}
  <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #D97706; border: 1px solid rgba(245, 158, 11, 0.3); font-weight: 700; font-size: var(--text-xs);">
    ★ {{ rating_summary.average_score }} ({{ rating_summary.rating_count }} {% trans "ratings" %})
  </span>
  {% for tag in rating_summary.top_tags %}
    <span class="badge" style="font-size: 11px; background: var(--bg-subtle); color: var(--text-muted); border: 1px solid var(--border-color);">
      {{ tag }}
    </span>
  {% endfor %}
{% endif %}
```

---

## 2. Modal Template (`templates/includes/rating_modal.html`)
The modal file is preserved at [`templates/includes/rating_modal.html`](file:///C:/Users/amite/.gemini/antigravity/scratch/nearby_chat/templates/includes/rating_modal.html).

---

## 3. View Logic (`apps/accounts/views.py`)
```python
if not is_blocked and request.user.is_authenticated:
    unrated_conv = ChatService.get_unrated_qualifying_conversation(request.user, target_user)
    if unrated_conv:
        can_rate = True
        unrated_conversation_id = str(unrated_conv.id)
```

---

## 4. Backend Service Methods (`apps/chat/services.py`)
- `ChatService.get_unrated_qualifying_conversation(rater, ratee)`
- `ChatService.submit_conversation_rating(conversation_id, rater, ratee, score, tags)`
- `ChatService.get_user_rating_summary(user)`

---

## 5. API Endpoint (`apps/chat/views.py`)
- URL: `POST /chats/ratings/submit/`
- View: `submit_rating_view`
