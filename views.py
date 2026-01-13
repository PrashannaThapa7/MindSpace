import hmac
import hashlib
import base64
import uuid
import pickle
import os
import re
import json
from collections import Counter
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import (
    authenticate,
    login as auth_login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from groq import Groq

from .models import UserAnswer, Mood, ChatMessage, ChatSession, Journal, UserSettings, Subscription


# ── eSewa config ──────────────────────────────────────────────────────────────
ESEWA_PRODUCT_CODE = 'EPAYTEST'
ESEWA_SECRET_KEY   = os.environ.get('ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')
ESEWA_PAYMENT_URL  = 'https://rc-epay.esewa.com.np/api/epay/main/v2/form'
PLANS = {
    'monthly': {'amount': 199,  'days': 30},
    'yearly':  {'amount': 1499, 'days': 365},
}


def esewa_signature(message):
    key = ESEWA_SECRET_KEY.encode()
    msg = message.encode()
    return base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode()


# ── Auth ──────────────────────────────────────────────────────────────────────
def landing(request):
    return render(request, "mental/landing.html")


def login(request):
    if request.method == "POST":
        email    = request.POST.get('email')
        password = request.POST.get('password')

        if not email or not password:
            return render(request, "mental/login.html", {"error": "Please enter both email and password."})

        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            user = None

        if user is not None:
            auth_login(request, user)
            return redirect('dashboard')
        return render(request, "mental/login.html", {"error": "Invalid email or password."})

    return render(request, "mental/login.html")


def signup(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name')
        last_name  = request.POST.get('last_name')
        username   = request.POST.get('username')
        email      = request.POST.get('email')
        password1  = request.POST.get('password1')
        password2  = request.POST.get('password2')

        if password1 != password2:
            return render(request, "mental/signup.html", {"error": "Passwords do not match"})
        if User.objects.filter(username=username).exists():
            return render(request, "mental/signup.html", {"error": "Username already exists"})
        if User.objects.filter(email=email).exists():
            return render(request, "mental/signup.html", {"error": "Email already exists"})

        user = User.objects.create_user(
            username=username, email=email, password=password1,
            first_name=first_name, last_name=last_name,
        )
        auth_login(request, user)
        return redirect('questions')

    return render(request, "mental/signup.html")


def logout(request):
    auth_logout(request)
    return redirect('landing')


# ── Onboarding ────────────────────────────────────────────────────────────────
QUESTIONS = [
    {"q": "What is your age group?",                        "options": ["Under 18", "18-25", "26-40", "40+"]},
    {"q": "What is your current occupation?",               "options": ["Student", "Working", "Unemployed", "Other"]},
    {"q": "How would you describe your daily routine?",     "options": ["Very active", "Moderate", "Relaxed", "Irregular"]},
    {"q": "How often do you feel stressed?",                "options": ["Not at all", "Sometimes", "Often", "Always"]},
    {"q": "How often do you feel anxious or worried?",      "options": ["Not at all", "Sometimes", "Often", "Always"]},
    {"q": "How is your sleep quality?",                     "options": ["Good", "Average", "Poor", "Very bad"]},
    {"q": "Do you feel emotionally balanced most of the time?", "options": ["Yes", "Sometimes", "Rarely", "No"]},
    {"q": "What activities help you relax?",                "options": ["Music", "Exercise", "Reading", "Socializing"]},
    {"q": "Do you prefer talking or writing your thoughts?","options": ["Talking", "Writing", "Both", "None"]},
    {"q": "How would you like MindCare to support you?",    "options": ["Chat", "Tips", "Tracking", "All"]},
]


@login_required
def questions(request):
    step = int(request.GET.get('step', 0))

    if step >= len(QUESTIONS):
        return redirect('dashboard')

    if request.method == "POST":
        answer        = request.POST.get('answer')
        question_text = QUESTIONS[step]["q"]
        if answer:
            UserAnswer.objects.update_or_create(
                user=request.user, question=question_text,
                defaults={'answer': answer},
            )
        next_step = step + 1
        if next_step >= len(QUESTIONS):
            return redirect('dashboard')
        return redirect(f'/questions/?step={next_step}')

    return render(request, "mental/questions.html", {
        "question": QUESTIONS[step],
        "step": step,
        "total": len(QUESTIONS),
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    return render(request, "mental/dashboard.html")


# ── Profile ───────────────────────────────────────────────────────────────────
@login_required
def edit_profile(request):
    if request.method == "POST":
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name  = request.POST.get('last_name', '')
        request.user.email      = request.POST.get('email', '')
        request.user.save()
        return redirect('edit_profile')

    user_answers = UserAnswer.objects.filter(user=request.user)
    return render(request, 'mental/edit_profile.html', {'user_answers': user_answers})


@login_required
def change_password(request):
    error = success = None
    if request.method == "POST":
        current = request.POST.get('current_password')
        new1    = request.POST.get('new_password1')
        new2    = request.POST.get('new_password2')

        if not request.user.check_password(current):
            error = "Current password is incorrect."
        elif new1 != new2:
            error = "New passwords do not match."
        elif len(new1) < 8:
            error = "Password must be at least 8 characters."
        else:
            request.user.set_password(new1)
            request.user.save()
            update_session_auth_hash(request, request.user)
            success = "Password changed successfully!"

    return render(request, 'mental/change_password.html', {'error': error, 'success': success})


# ── Settings ──────────────────────────────────────────────────────────────────
@login_required
def settings(request):
    s, _ = UserSettings.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get('action')

        if action == 'save_settings':
            s.store_chat_history = 'store_chat_history' in request.POST
            s.journal_private    = 'journal_private'    in request.POST
            s.email_alerts       = 'email_alerts'       in request.POST
            s.weekly_summary     = 'weekly_summary'     in request.POST
            s.save()

        elif action == 'purge_data':
            Journal.objects.filter(user=request.user).delete()
            ChatMessage.objects.filter(user=request.user).delete()
            ChatSession.objects.filter(user=request.user).delete()

        elif action == 'delete_account':
            request.user.delete()
            return redirect('landing')

        return redirect('settings')

    return render(request, 'mental/settings.html', {'s': s})


# ── Mood ──────────────────────────────────────────────────────────────────────
@login_required
def save_mood(request):
    if request.method == "POST":
        mood = request.POST.get("mood")
        Mood.objects.create(user=request.user, mood=mood)
        return JsonResponse({"status": "success"})


@login_required
def mood_dashboard(request):
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    today = timezone.now().date()
    week_start = today - timedelta(days=6)  # last 7 days including today

    # All moods in the last 7 days
    recent_moods = Mood.objects.filter(
        user=request.user,
        date__date__gte=week_start,
    ).order_by('date')

    # Today's check-ins
    todays_moods = Mood.objects.filter(
        user=request.user,
        date__date=today,
    ).order_by('date')

    # Most common mood overall
    most_common = (
        Mood.objects.filter(user=request.user)
        .values('mood')
        .annotate(count=Count('mood'))
        .order_by('-count')
        .first()
    )

    # Total check-ins ever
    total_checkins = Mood.objects.filter(user=request.user).count()

    # Current streak: consecutive days with at least one mood logged
    streak = 0
    check_day = today
    while True:
        if Mood.objects.filter(user=request.user, date__date=check_day).exists():
            streak += 1
            check_day -= timedelta(days=1)
        else:
            break

    # Build 7-day chart data (count per day)
    days_labels = []
    days_counts = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        days_labels.append(day.strftime('%a'))
        days_counts.append(
            Mood.objects.filter(user=request.user, date__date=day).count()
        )

    # Mood emoji map
    MOOD_EMOJI = {
        'happy':   '😊', 'neutral': '😐', 'sad':    '😔',
        'angry':   '😤', 'tired':   '😴', 'anxious':'😰',
    }

    return render(request, "mental/mood_dashboard.html", {
        'todays_moods':  todays_moods,
        'most_common':   most_common,
        'total_checkins': total_checkins,
        'streak':        streak,
        'days_labels':   days_labels,
        'days_counts':   days_counts,
        'mood_emoji':    MOOD_EMOJI,
    })


# ── Chat ──────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
model_path  = os.path.join(BASE_DIR, 'mental', 'ml_models', 'emotion_model.pkl')
vector_path = os.path.join(BASE_DIR, 'mental', 'ml_models', 'vectorizer.pkl')

with open(model_path, 'rb') as f:
    emotion_model = pickle.load(f)
with open(vector_path, 'rb') as f:
    vectorizer = pickle.load(f)

client = Groq(api_key=os.environ.get('GROQ_API_KEY', ''))


def clean_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def chat(request):
    sessions = (
        ChatSession.objects.filter(user=request.user).order_by('-created_at')
        if request.user.is_authenticated else []
    )
    return render(request, "mental/chat.html", {'sessions': sessions})


@login_required
def chat_api(request):
    if request.method == "POST":
        user_text  = request.POST.get('message', '').strip()
        session_id = request.POST.get('session_id')

        session = None
        if session_id:
            session = ChatSession.objects.filter(id=session_id, user=request.user).first()
        if not session:
            session = ChatSession.objects.create(user=request.user, title=user_text[:40])
        elif session.title == 'New Chat':
            session.title = user_text[:40]
            session.save()

        cleaned   = clean_text(user_text)
        vector    = vectorizer.transform([cleaned])
        probs     = emotion_model.predict_proba(vector)[0]
        max_prob  = max(probs)

        if max_prob < 0.45 or len(user_text) < 3:
            emotion       = "Unclear"
            system_prompt = (
                "You are a warm, caring friend. The user sent something unclear. "
                "Just gently ask them what's on their mind. Keep it very short and natural."
            )
        else:
            emotion       = emotion_model.predict(vector)[0]
            system_prompt = (
                "You are a warm, caring best friend who listens without judgment. "
                "Respond to what the user said naturally and empathetically. "
                "NEVER say things like 'you seem happy', 'you sound sad', 'I can tell you feel', "
                "'it sounds like you are feeling', or any assumption about their emotion. "
                "Just respond to what they actually said, like a real friend would in a text message. "
                "No bullet points, no formal language, no AI phrases. "
                "Keep it to 2-3 sentences and ask one gentle follow-up question."
            )

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            temperature=0.9,
        )
        ai_reply = completion.choices[0].message.content

        ChatMessage.objects.create(
            user=request.user, session=session,
            message=user_text, response=ai_reply,
            detected_emotion=emotion,
        )

        return JsonResponse({
            'reply': ai_reply,
            'session_id': session.id,
            'session_title': session.title,
        })


def save_session_to_journal(session, user):
    msgs = ChatMessage.objects.filter(session=session).order_by('created_at')
    if not msgs.exists():
        return
    content  = '\n\n'.join(f"Me: {m.message}\nAI: {m.response}" for m in msgs)
    emotions = [m.detected_emotion for m in msgs if m.detected_emotion and m.detected_emotion != 'Unclear']
    mood     = Counter(emotions).most_common(1)[0][0] if emotions else ''
    Journal.objects.update_or_create(
        user=user, source='chat', title=f"Chat: {session.title}",
        defaults={'content': content, 'mood': mood},
    )


@login_required
def new_chat_session(request):
    if request.method == "POST":
        prev_session_id = request.POST.get('prev_session_id')
        if prev_session_id:
            prev = ChatSession.objects.filter(id=prev_session_id, user=request.user).first()
            if prev:
                save_session_to_journal(prev, request.user)
        return JsonResponse({'ok': True})


@login_required
def get_chat_history(request):
    session_id = request.GET.get('session_id')
    if session_id:
        msgs = ChatMessage.objects.filter(session_id=session_id, user=request.user).order_by('created_at')
    else:
        msgs = ChatMessage.objects.filter(user=request.user).order_by('created_at')[:30]
    history = []
    for m in msgs:
        history.append({'role': 'user', 'text': m.message})
        history.append({'role': 'bot',  'text': m.response})
    return JsonResponse({'history': history})


# ── Journal ───────────────────────────────────────────────────────────────────
@login_required
def journal(request):
    sub = Subscription.objects.filter(
        user=request.user, is_active=True, expires_at__gt=timezone.now()
    ).first()
    if not sub:
        return redirect('subscribe')

    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'save':
            Journal.objects.create(
                user=request.user,
                title=request.POST.get('title', '').strip(),
                content=request.POST.get('content', '').strip(),
                mood=request.POST.get('mood', '').strip(),
                source='manual',
            )
        elif action == 'delete':
            Journal.objects.filter(id=request.POST.get('id'), user=request.user).delete()
        return redirect('journal')

    all_entries   = Journal.objects.filter(user=request.user).order_by('-created_at')
    chat_sessions = (
        ChatSession.objects.filter(user=request.user, messages__isnull=False)
        .distinct().order_by('-created_at')
    )
    moods = [('😊','Happy'),('😐','Neutral'),('😔','Sad'),('😤','Angry'),('😰','Anxious'),('😴','Tired')]
    return render(request, 'mental/journal.html', {
        'all_entries':     all_entries,
        'chat_entries':    all_entries.filter(source='chat'),
        'writing_entries': all_entries.filter(source='manual'),
        'chat_sessions':   chat_sessions,
        'prompt':          request.GET.get('title', ''),
        'moods':           moods,
    })


@login_required
def save_chat_as_journal(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        session    = ChatSession.objects.filter(id=session_id, user=request.user).first()
        if session:
            msgs    = ChatMessage.objects.filter(session=session).order_by('created_at')
            content = '\n\n'.join(f"Me: {m.message}\nAI: {m.response}" for m in msgs)
            Journal.objects.create(
                user=request.user,
                title=f"Chat: {session.title}",
                content=content,
                source='chat',
            )
        return redirect('journal')


# ── Subscribe / eSewa ─────────────────────────────────────────────────────────
@login_required
def subscribe(request):
    plans_context = {}
    for plan_key, plan_data in PLANS.items():
        amount   = plan_data['amount']
        tx_uuid  = f"SUB-{plan_key[0].upper()}-{request.user.id}-{uuid.uuid4().hex[:8].upper()}"
        message  = f"total_amount={amount},transaction_uuid={tx_uuid},product_code={ESEWA_PRODUCT_CODE}"
        plans_context[plan_key] = {
            'amount':    amount,
            'days':      plan_data['days'],
            'tx_uuid':   tx_uuid,
            'signature': esewa_signature(message),
        }
    return render(request, 'mental/subscribe.html', {
        'plans':       plans_context,
        'product_code': ESEWA_PRODUCT_CODE,
        'payment_url':  ESEWA_PAYMENT_URL,
        'success_url':  request.build_absolute_uri('/esewa/success/'),
        'failure_url':  request.build_absolute_uri('/esewa/failure/'),
    })


@login_required
def esewa_success(request):
    data = request.GET.get('data', '')
    if not data:
        return redirect('subscribe')
    try:
        decoded = json.loads(base64.b64decode(data + '==').decode())

        # Verify eSewa's HMAC signature to prevent fake callbacks
        signed_fields = decoded.get('signed_field_names', '')
        if signed_fields:
            field_list   = [f.strip() for f in signed_fields.split(',')]
            message      = ','.join(f"{f}={decoded.get(f, '')}" for f in field_list)
            expected_sig = esewa_signature(message)
            received_sig = decoded.get('signature', '')
            if not hmac.compare_digest(expected_sig, received_sig):
                return redirect('esewa_failure')

        tx_uuid = decoded.get('transaction_uuid', '')
        plan    = 'yearly' if tx_uuid.startswith('SUB-Y-') else 'monthly'
        days    = PLANS[plan]['days']

        sub, _ = Subscription.objects.get_or_create(user=request.user)
        sub.plan       = plan
        sub.is_active  = True
        sub.expires_at = timezone.now() + timedelta(days=days)
        sub.save()
    except Exception:
        pass
    return redirect('journal')


@login_required
def esewa_failure(request):
    return render(request, 'mental/esewa_failure.html')


# ── Static pages ──────────────────────────────────────────────────────────────
def resources(request):
    return render(request, "mental/resources.html")


def privacy(request):
    return render(request, "mental/privacy.html")
