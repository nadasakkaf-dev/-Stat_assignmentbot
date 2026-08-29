import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from database import (
    init_db,
    add_submission,
    get_stats,
    get_submissions,
    get_missing_students,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# مراحل المحادثة
NAME, FILE = range(2)

# إعدادات البوت
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "50"))


def valid_file(document):
    """
    السماح فقط بملفات ZIP و RAR
    """
    if not document:
        return False

    if not document.file_name:
        return False

    extension = os.path.splitext(document.file_name)[1].lower()

    return extension in [".zip", ".rar"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بداية تسليم المشروع
    """

    context.user_data.clear()

    await update.message.reply_text(
        "🎓 أهلاً بك في بوت تسليم مشروع المقرر\n\n"
        "هذا البوت مخصص لاستلام مشروع المقرر فقط.\n\n"
        "👤 يرجى كتابة اسمك الكامل:"
    )

    return NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    استقبال اسم الطالب
    """

    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(
            "❌ الاسم قصير جدًا.\n"
            "يرجى كتابة اسمك الكامل."
        )

        return NAME

    if len(name) > 120:
        await update.message.reply_text(
            "❌ الاسم طويل جدًا.\n"
            "يرجى كتابة الاسم بشكل مختصر."
        )

        return NAME

    context.user_data["student_name"] = name

    await update.message.reply_text(
        f"مرحبًا {name} 👋\n\n"
        "📦 الآن أرسل مشروع المقرر.\n\n"
        "يجب أن يكون الملف مضغوطًا بإحدى الصيغتين:\n"
        "✅ ZIP\n"
        "✅ RAR"
    )

    return FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    استقبال ملف المشروع
    """

    document = update.message.document

    # التحقق من نوع الملف
    if not valid_file(document):

        await update.message.reply_text(
            "❌ الملف غير مقبول.\n\n"
            "يجب إرسال مشروع المقرر كملف:\n"
            "📦 ZIP أو RAR"
        )

        return FILE

    # التحقق من حجم الملف
    max_bytes = MAX_FILE_MB * 1024 * 1024

    if document.file_size and document.file_size > max_bytes:

        await update.message.reply_text(
            f"❌ حجم الملف أكبر من الحد المسموح.\n\n"
            f"الحد الحالي: {MAX_FILE_MB} MB"
        )

        return FILE

    student_name = context.user_data.get("student_name")

    if not student_name:

        await update.message.reply_text(
            "❌ انتهت جلسة التسليم.\n\n"
            "أرسل /start للبدء من جديد."
        )

        return ConversationHandler.END

    user = update.effective_user

    submission_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:

        # حفظ معلومات التسليم
        submission_id = add_submission(
            student_name=student_name,
            telegram_user_id=user.id,
            file_name=document.file_name,
            file_id=document.file_id,
            submitted_at=submission_time,
        )

        # إرسال المشروع إلى المسؤول
        if ADMIN_ID:

            await context.bot.send_chat_action(
                chat_id=ADMIN_ID,
                action=ChatAction.UPLOAD_DOCUMENT,
            )

            caption = (
                "📥 تسليم جديد لمشروع المقرر\n\n"
                f"👤 الطالب: {student_name}\n"
                f"📎 الملف: {document.file_name}\n"
                f"🕐 وقت التسليم: {submission_time}\n"
                f"🆔 رقم التسليم: {submission_id}"
            )

            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=document.file_id,
                caption=caption,
            )

        # تأكيد للطالب
        await update.message.reply_text(
            "✅ تم استلام مشروعك بنجاح.\n\n"
            f"👤 الاسم: {student_name}\n"
            f"📎 الملف: {document.file_name}\n"
            f"🕐 وقت التسليم: {submission_time}\n\n"
            "يرجى الاحتفاظ بهذه الرسالة."
        )

    except Exception as error:

        logger.exception(
            "حدث خطأ أثناء حفظ التسليم: %s",
            error,
        )

        await update.message.reply_text(
            "❌ حدث خطأ أثناء استلام المشروع.\n\n"
            "يرجى المحاولة مرة أخرى."
        )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إلغاء التسليم
    """

    context.user_data.clear()

    await update.message.reply_text(
        "تم إلغاء عملية التسليم.\n\n"
        "يمكنك البدء مرة أخرى باستخدام /start"
    )

    return ConversationHandler.END


def is_admin(update: Update):
    """
    التحقق من أن المستخدم هو المسؤول
    """

    if not ADMIN_ID:
        return False

    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_ID


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إحصائيات التسليم
    """

    if not is_admin(update):
        return

    total, students = get_stats()

    await update.message.reply_text(
        "📊 إحصائيات مشروع المقرر\n\n"
        f"📥 إجمالي التسليمات: {total}\n"
        f"👥 عدد الطلاب الذين سلّموا: {students}"
    )


async def submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض التسليمات
    """

    if not is_admin(update):
        return

    rows = get_submissions()

    if not rows:

        await update.message.reply_text(
            "📭 لا توجد تسليمات حتى الآن."
        )

        return

    message = "📋 تسليمات مشروع المقرر:\n\n"

    for row in rows:

        submission_id = row[0]
        student_name = row[1]
        file_name = row[2]
        submitted_at = row[3]

        line = (
            f"🆔 #{submission_id}\n"
            f"👤 {student_name}\n"
            f"📎 {file_name}\n"
            f"🕐 {submitted_at}\n\n"
        )

        if len(message) + len(line) > 3500:

            await update.message.reply_text(message)

            message = ""

        message += line

    if message:

        await update.message.reply_text(message)


async def missing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    الطلاب الذين لم يسلموا
    """

    if not is_admin(update):
        return

    names = get_missing_students()

    if not names:

        await update.message.reply_text(
            "✅ لا توجد أسماء ناقصة.\n\n"
            "تأكد من أن ملف students.txt يحتوي على أسماء الطلاب."
        )

        return

    message = "👥 الطلاب الذين لم يسلّموا:\n\n"

    for name in names:

        message += f"• {name}\n"

    await update.message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تعليمات البوت
    """

    await update.message.reply_text(
        "🎓 بوت تسليم مشروع المقرر\n\n"
        "📤 لتسليم المشروع:\n"
        "استخدم /start\n\n"
        "📦 نوع الملف المقبول:\n"
        "ZIP أو RAR\n\n"
        "❌ لا ترسل ملفات غير مضغوطة."
    )


async def error_handler(update, context):
    """
    معالجة الأخطاء
    """

    logger.exception(
        "حدث خطأ غير متوقع:",
        exc_info=context.error,
    )


def main():

    # قراءة Token من .env
    token = os.getenv("BOT_TOKEN")

    if not token:

        raise RuntimeError(
            "لم يتم العثور على BOT_TOKEN. "
            "أضفه في متغيرات البيئة."
        )

    # إنشاء قاعدة البيانات
    init_db()

    # إنشاء التطبيق
    application = (
        Application.builder()
        .token(token)
        .build()
    )

    # محادثة الطالب
    conversation = ConversationHandler(

        entry_points=[
            CommandHandler("start", start)
        ],

        states={

            NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_name,
                )
            ],

            FILE: [
                MessageHandler(
                    filters.Document.ALL,
                    receive_file,
                )
            ],
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ],

        allow_reentry=True,
    )

    # إضافة handlers
    application.add_handler(conversation)

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("stats", stats)
    )

    application.add_handler(
        CommandHandler("submissions", submissions)
    )

    application.add_handler(
        CommandHandler("missing", missing)
    )

    application.add_error_handler(error_handler)

    print("Bot is running...")

    # تشغيل البوت
    application.run_polling()


if __name__ == "__main__":
    main()
