import logging
import os
import math
import ffmpeg

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define states for the conversation
(GET_VIDEO, GET_TITLE, GET_CHANNEL, 
 GET_DURATION, GET_COLOR) = range(5)

# --- Conversation Functions ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks for a video."""
    await update.message.reply_text(
        "Hi! I can split your video into clips with a custom layout.\n\n"
        "Please send me the video you want to process. "
        "For best results on this platform, please keep videos under 5-10 minutes."
    )
    return GET_VIDEO

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the video and asks for a title."""
    video_file = await update.message.video.get_file()
    video_path = f"{video_file.file_id}.mp4"
    await video_file.download_to_drive(video_path)
    
    context.user_data['video_path'] = video_path
    
    await update.message.reply_text(
        "Great! Now, what should be the main title for the clips? (e.g., 'Best of Animated')"
    )
    return GET_TITLE

async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the title and asks for the channel name."""
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Got it. What is your channel/username? (e.g., '@Alokchauhan1100')")
    return GET_CHANNEL

async def get_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the channel name and asks for clip duration."""
    context.user_data['channel'] = update.message.text
    await update.message.reply_text("Perfect. What duration (in seconds) should each clip be? (e.g., 60)")
    return GET_DURATION

async def get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the duration and asks for the background color."""
    try:
        context.user_data['duration'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("That's not a valid number. Please enter the duration in seconds.")
        return GET_DURATION
        
    await update.message.reply_text(
        "Almost done! What background color would you like?\n\n"
        "You can use a name (e.g., `orange`, `blue`) or a hex code (e.g., `#FAD9A1`)."
    )
    return GET_COLOR

async def get_color_and_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the color and starts the video processing job."""
    context.user_data['color'] = update.message.text
    
    await update.message.reply_text(
        "All set! I'm starting to process your video. This might take a while.\n\n"
        "I'll send you each clip as soon as it's ready."
    )
    
    # --- The Core Processing Logic ---
    try:
        user_data = context.user_data
        video_path = user_data['video_path']
        clip_duration = user_data['duration']

        # Get video properties
        probe = ffmpeg.probe(video_path)
        total_duration = float(probe['format']['duration'])
        num_clips = math.ceil(total_duration / clip_duration)
        
        await update.message.reply_text(f"Video detected. Total duration: {total_duration:.2f}s. I will create {num_clips} clips.")

        for i in range(num_clips):
            part_num = i + 1
            start_time = i * clip_duration
            output_filename = f"part_{part_num}_{context._user_id}.mp4"
            
            await update.message.reply_text(f"Processing Part {part_num}/{num_clips}...")

            # Define streams
            input_stream = ffmpeg.input(video_path, ss=start_time, t=clip_duration)
            video_clip = input_stream.video.scale(1000, -1) # Scale video to fit
            audio_clip = input_stream.audio

            # Create background
            background = ffmpeg.input(f"color=c={user_data['color']}:s=1080x1920", f='lavfi', t=clip_duration)

            # Overlay video on background
            processed_video = ffmpeg.overlay(background, video_clip, x='(W-w)/2', y='(H-h)/2')

            # Add text (Title, Channel, Part)
            # Make sure the font file is in the 'fonts' directory
            font_path = 'fonts/LiberationSans-Regular.ttf'
            
            processed_video = ffmpeg.drawtext(
                processed_video,
                text=user_data['title'],
                x='(w-text_w)/2',
                y='(h-text_h)/2 - 700',
                fontsize=70,
                fontcolor='black',
                fontfile=font_path
            )
            processed_video = ffmpeg.drawtext(
                processed_video,
                text=user_data['channel'],
                x='40',
                y='40',
                fontsize=40,
                fontcolor='white',
                fontfile=font_path,
                box=1, boxcolor='black@0.5', boxborderw=10 # Add a box for readability
            )
            processed_video = ffmpeg.drawtext(
                processed_video,
                text=f"PART {part_num}",
                x='(w-text_w)/2',
                y='(h-text_h)/2 + 700',
                fontsize=60,
                fontcolor='black',
                fontfile=font_path
            )

            # Combine video and audio and run
            output = ffmpeg.output(processed_video, audio_clip, output_filename, vcodec='libx264', acodec='aac', preset='fast', movflags='frag_keyframe+empty_moov')
            ffmpeg.run(output, overwrite_output=True)

            # Send the clip
            with open(output_filename, 'rb') as video_part:
                await context.bot.send_video(chat_id=update.effective_chat.id, video=video_part, supports_streaming=True)
            
            # Clean up the generated clip
            os.remove(output_filename)

        await update.message.reply_text("All done! I have sent you all the clips.")

    except Exception as e:
        logger.error(f"Error during processing: {e}")
        await update.message.reply_text(f"An error occurred during processing: {e}\nPlease try again.")
    finally:
        # Clean up the original uploaded video
        if os.path.exists(context.user_data['video_path']):
            os.remove(context.user_data['video_path'])

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    # Clean up any downloaded file if conversation is cancelled
    if 'video_path' in context.user_data and os.path.exists(context.user_data['video_path']):
        os.remove(context.user_data['video_path'])
        
    await update.message.reply_text(
        "Operation cancelled. Send /start to begin again."
    )
    return ConversationHandler.END


def main() -> None:
    """Run the bot."""
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        raise ValueError("No TOKEN found in environment variables!")

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_VIDEO: [MessageHandler(filters.VIDEO, get_video)],
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            GET_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_channel)],
            GET_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duration)],
            GET_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_color_and_process)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
