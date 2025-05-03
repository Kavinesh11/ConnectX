



# -----------------------------------------
import os
import cv2 # type: ignore
import time
import argparse
import numpy as np # type: ignore
from dotenv import load_dotenv # type: ignore
from google import genai
from google.genai import types # type: ignore

from calendar_scheduler import schedule_if_meeting

load_dotenv()

def extract_last_frame_per_second(video_path, output_folder=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps
    print(f"Video info: {frame_count} frames, {fps:.2f} FPS, {duration:.2f} seconds")

    if output_folder is None:
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_folder = f"{video_name}_frames"

    os.makedirs(output_folder, exist_ok=True)

    saved_frames = []
    current_second = 0
    frames_in_current_second = []

    frame_index = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_time = frame_index / fps
        second_of_frame = int(current_time)

        if second_of_frame == current_second:
            frames_in_current_second.append((frame_index, frame))
        else:
            if frames_in_current_second:
                last_frame_index, last_frame = frames_in_current_second[-1]
                frame_path = os.path.join(output_folder, f"second_{current_second}frame{last_frame_index}.jpg")
                cv2.imwrite(frame_path, last_frame)
                saved_frames.append(frame_path)
                print(f"Saved last frame of second {current_second} (frame #{last_frame_index})")

            current_second = second_of_frame
            frames_in_current_second = [(frame_index, frame)]

        frame_index += 1

    if frames_in_current_second:
        last_frame_index, last_frame = frames_in_current_second[-1]
        frame_path = os.path.join(output_folder, f"second_{current_second}frame{last_frame_index}.jpg")
        cv2.imwrite(frame_path, last_frame)
        saved_frames.append(frame_path)
        print(f"Saved last frame of second {current_second} (frame #{last_frame_index})")

    cap.release()
    print(f"Extracted {len(saved_frames)} frames (one per second) to {output_folder}")
    return saved_frames

def get_caption_from_gemini(image_path, gemini_api_key):
    client = genai.Client(api_key=gemini_api_key)
    uploaded_file = client.files.upload(file=image_path)
    model = "gemini-2.0-flash"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=uploaded_file.uri,
                    mime_type=uploaded_file.mime_type,
                ),
                types.Part.from_text(text="Extract the caption or conversation context from this image."),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(response_mime_type="text/plain")

    full_response = ""
    try:
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.text:
                full_response += chunk.text
                print(chunk.text, end="")
        print()
    except Exception as e:
        print(f"Error getting caption: {e}")
        return f"Error: {str(e)}"

    return full_response.strip()

def extract_existing_captions(markdown_file):
    if not os.path.exists(markdown_file):
        return []

    with open(markdown_file, 'r') as f:
        content = f.read()

    captions = []
    lines = content.split('\n')
    capturing = False
    current_caption = []

    for line in lines:
        if line.startswith('## Frame:'):
            if current_caption:
                captions.append('\n'.join(current_caption).strip())
                current_caption = []
            capturing = True
        elif line.startswith('*Source image:'):
            if current_caption:
                captions.append('\n'.join(current_caption).strip())
                current_caption = []
            capturing = False
        elif capturing and line and not line.startswith('#') and not line == '---':
            current_caption.append(line)

    if current_caption:
        captions.append('\n'.join(current_caption).strip())

    return captions

def check_caption_similarity_with_gemini(new_caption, existing_captions, gemini_api_key):
    if not existing_captions:
        return False

    client = genai.Client(api_key=gemini_api_key)
    model = "gemini-2.0-flash"

    prompt = f"""Compare the following new caption with the list of existing captions. 
Determine if the new caption is semantically similar to any of the existing ones.
Answer only with "YES" or "NO".

New caption: "{new_caption}"

Existing captions:
"""
    for i, caption in enumerate(existing_captions):
        prompt += f"{i+1}. \"{caption}\"\n"

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    config = types.GenerateContentConfig(response_mime_type="text/plain")

    try:
        response = client.models.generate_content(model=model, contents=contents, config=config)
        result = response.text.strip().upper()
        print(f"Gemini similarity check result: {result}")
        return result == "YES"
    except Exception as e:
        print(f"Error in similarity check: {e}")
        return False

def update_markdown(caption, markdown_file, image_path, gemini_api_key):
    if not os.path.exists(markdown_file):
        with open(markdown_file, 'w') as f:
            f.write("# Video Frame Captions\n\n")

    existing_captions = extract_existing_captions(markdown_file)
    if existing_captions and check_caption_similarity_with_gemini(caption, existing_captions, gemini_api_key):
        print(f"Gemini determined that a similar caption already exists for {image_path}. Skipping.")
        return False

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    frame_info = os.path.basename(image_path)

    with open(markdown_file, 'a') as f:
        f.write(f"\n## Frame: {frame_info} (Added: {timestamp})\n\n")
        f.write(f"{caption}\n\n")
        f.write(f"Source image: {image_path}\n\n")
        f.write("---\n")

    print(f"✅ Added new caption for {image_path}")
    return True

def process_video_frames(video_path, markdown_file, gemini_api_key, output_folder=None):
    frame_paths = extract_last_frame_per_second(video_path, output_folder)
    total_frames = len(frame_paths)
    new_captions = 0

    for i, frame_path in enumerate(frame_paths):
        print(f"\n🔍 Processing frame {i+1}/{total_frames}: {frame_path}")
        caption = get_caption_from_gemini(frame_path, gemini_api_key)

        if update_markdown(caption, markdown_file, frame_path, gemini_api_key):
            new_captions += 1
            try:
                gemini_client = genai.Client(api_key=gemini_api_key)
                schedule_if_meeting(caption, gemini_client)
            except Exception as e:
                print(f"⚠️ Could not schedule meeting: {e}")

    print(f"\n📊 Summary: Processed {total_frames} frames, added {new_captions} new captions")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames from video and caption them using Gemini")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output", "-o", help="Output folder for frames (optional)")
    parser.add_argument("--markdown", "-m", default="video_captions.md",
                        help="Path to markdown file for captions (default: video_captions.md)")
    parser.add_argument("--api-key", "-k", help="Gemini API key (optional, or use GEMINI_API_KEY env var)")

    args = parser.parse_args()

    gemini_api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("Gemini API key must be provided via --api-key or .env file")

    process_video_frames(args.video_path, args.markdown, gemini_api_key, args.output)





#-----------------------------------------------------------------------------------------------------------------------------------
# import cv2
# import os
# import numpy as np
# import base64
# from google import genai
# from google.genai import types
# import argparse
# import time
# from dotenv import load_dotenv

# load_dotenv() 


# def extract_last_frame_per_second(video_path, output_folder=None):
#     """
#     Extracts the last frame from each second of video and saves as images.
    
#     Args:
#         video_path (str): Path to the input video file
#         output_folder (str, optional): Folder to save extracted frames. 
#                                        If None, creates a folder based on video name.
    
#     Returns:
#         list: Paths to all saved frame images
#     """
#     # Open the video file
#     cap = cv2.VideoCapture(video_path)
    
#     # Check if the video opened successfully
#     if not cap.isOpened():
#         print(f"Error: Could not open video file {video_path}")
#         return []
    
#     # Get video properties
#     fps = cap.get(cv2.CAP_PROP_FPS)
#     frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#     duration = frame_count / fps
    
#     print(f"Video info: {frame_count} frames, {fps} FPS, {duration:.2f} seconds")
    
#     # Create output directory
#     if output_folder is None:
#         video_name = os.path.splitext(os.path.basename(video_path))[0]
#         output_folder = f"{video_name}_frames"
    
#     os.makedirs(output_folder, exist_ok=True)
    
#     saved_frames = []
#     current_second = 0
#     frames_in_current_second = []
    
#     frame_index = 0
#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             break
        
#         # Calculate the current time in seconds
#         current_time = frame_index / fps
#         second_of_frame = int(current_time)
        
#         # If we're still in the same second, add this frame
#         if second_of_frame == current_second:
#             frames_in_current_second.append((frame_index, frame))
#         else:
#             # We've moved to a new second, save the last frame from the previous second
#             if frames_in_current_second:
#                 last_frame_index, last_frame = frames_in_current_second[-1]
#                 frame_path = os.path.join(output_folder, f"second_{current_second}frame{last_frame_index}.jpg")
#                 cv2.imwrite(frame_path, last_frame)
#                 saved_frames.append(frame_path)
#                 print(f"Saved last frame of second {current_second} (frame #{last_frame_index})")
            
#             # Reset for the new second
#             current_second = second_of_frame
#             frames_in_current_second = [(frame_index, frame)]
        
#         frame_index += 1
    
#     # Save the last frame from the last second
#     if frames_in_current_second:
#         last_frame_index, last_frame = frames_in_current_second[-1]
#         frame_path = os.path.join(output_folder, f"second_{current_second}frame{last_frame_index}.jpg")
#         cv2.imwrite(frame_path, last_frame)
#         saved_frames.append(frame_path)
#         print(f"Saved last frame of second {current_second} (frame #{last_frame_index})")
    
#     # Release video capture
#     cap.release()
    
#     print(f"Extracted {len(saved_frames)} frames (one per second) to {output_folder}")
#     return saved_frames

# def get_caption_from_gemini(image_path, gemini_api_key):
#     """
#     Get caption for an image using Gemini API
    
#     Args:
#         image_path (str): Path to the image file
#         gemini_api_key (str): Gemini API key
        
#     Returns:
#         str: Caption for the image
#     """
#     client = genai.Client(api_key=gemini_api_key)
    
#     # Upload the file
#     uploaded_file = client.files.upload(file=image_path)
    
#     model = "gemini-2.0-flash"
#     contents = [
#         types.Content(
#             role="user",
#             parts=[
#                 types.Part.from_uri(
#                     file_uri=uploaded_file.uri,
#                     mime_type=uploaded_file.mime_type,
#                 ),
#                 types.Part.from_text(text="Extract the captions from this image"),
#             ],
#         ),
#     ]
    
#     generate_content_config = types.GenerateContentConfig(
#         response_mime_type="text/plain",
#     )
    
#     # Collect all text parts from the streaming response
#     full_response = ""
#     try:
#         for chunk in client.models.generate_content_stream(
#             model=model,
#             contents=contents,
#             config=generate_content_config,
#         ):
#             if chunk.text:
#                 full_response += chunk.text
#                 print(chunk.text, end="")
#         print()  # Add a newline after response
#     except Exception as e:
#         print(f"Error getting caption: {e}")
#         return f"Error: {str(e)}"
    
#     return full_response.strip()

# def check_caption_similarity_with_gemini(new_caption, existing_captions, gemini_api_key):
#     """
#     Use Gemini to check if a caption is semantically similar to any existing captions
    
#     Args:
#         new_caption (str): The new caption to check
#         existing_captions (list): List of existing captions
#         gemini_api_key (str): Gemini API key
        
#     Returns:
#         bool: True if the caption is similar to an existing one, False otherwise
#     """
#     if not existing_captions:
#         return False
        
#     client = genai.Client(api_key=gemini_api_key)
#     model = "gemini-2.0-flash"
    
#     # Prepare the prompt for Gemini
#     prompt = f"""Compare the following new caption with the list of existing captions. 
# Determine if the new caption is semantically similar to any of the existing ones.
# Answer with only "YES" if similar, or "NO" if not similar.

# New caption: "{new_caption}"

# Existing captions:
# """
    
#     # Add existing captions to the prompt
#     for i, caption in enumerate(existing_captions):
#         prompt += f"{i+1}. \"{caption}\"\n"
    
#     contents = [
#         types.Content(
#             role="user",
#             parts=[types.Part.from_text(text=prompt)],
#         ),
#     ]
    
#     generate_content_config = types.GenerateContentConfig(
#         response_mime_type="text/plain",
#     )
    
#     # Get response from Gemini
#     try:
#         response = client.models.generate_content(
#             model=model,
#             contents=contents,
#             config=generate_content_config,
#         )
        
#         result = response.text.strip().upper()
#         print(f"Gemini similarity check result: {result}")
        
#         return result == "YES"
#     except Exception as e:
#         print(f"Error in similarity check: {e}")
#         # If there's an error, assume it's not a duplicate to be safe
#         return False

# def extract_existing_captions(markdown_file):
#     """
#     Extract existing captions from the markdown file
    
#     Args:
#         markdown_file (str): Path to markdown file
        
#     Returns:
#         list: List of existing captions
#     """
#     if not os.path.exists(markdown_file):
#         return []
        
#     with open(markdown_file, 'r') as f:
#         content = f.read()
    
#     # Simple extraction of caption text - this is basic and could be improved
#     # We're looking for text between frame headings and source images
#     captions = []
#     lines = content.split('\n')
    
#     capturing = False
#     current_caption = []
    
#     for line in lines:
#         if line.startswith('## Frame:'):
#             # Start of a new caption section
#             if current_caption:
#                 captions.append('\n'.join(current_caption).strip())
#                 current_caption = []
#             capturing = True
#         elif line.startswith('*Source image:'):
#             # End of caption
#             if current_caption:
#                 captions.append('\n'.join(current_caption).strip())
#                 current_caption = []
#             capturing = False
#         elif capturing and line and not line.startswith('#') and not line == '---':
#             current_caption.append(line)
    
#     # Add the last caption if there is one
#     if current_caption:
#         captions.append('\n'.join(current_caption).strip())
    
#     return captions

# def update_markdown(caption, markdown_file, image_path, gemini_api_key):
#     """
#     Update markdown file with the caption if it doesn't already exist according to Gemini
    
#     Args:
#         caption (str): Caption to add
#         markdown_file (str): Path to markdown file
#         image_path (str): Path to the image (for reference)
#         gemini_api_key (str): Gemini API key
        
#     Returns:
#         bool: True if caption was added, False if it was a duplicate
#     """
#     # Create file if it doesn't exist
#     if not os.path.exists(markdown_file):
#         with open(markdown_file, 'w') as f:
#             f.write("# Video Frame Captions\n\n")
    
#     # Extract existing captions
#     existing_captions = extract_existing_captions(markdown_file)
    
#     # Use Gemini to check if this caption is similar to any existing ones
#     if existing_captions and check_caption_similarity_with_gemini(caption, existing_captions, gemini_api_key):
#         print(f"Gemini determined that a similar caption already exists for {image_path}. Skipping.")
#         return False
    
#     # Add new caption with timestamp and image reference
#     timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#     frame_info = os.path.basename(image_path)
    
#     with open(markdown_file, 'a') as f:
#         f.write(f"\n## Frame: {frame_info} (Added: {timestamp})\n\n")
#         f.write(f"{caption}\n\n")
#         f.write(f"Source image: {image_path}\n\n")
#         f.write("---\n")
    
#     print(f"Added new caption for {image_path}")
#     return True

# def process_video_frames(video_path, markdown_file, gemini_api_key, output_folder=None):
#     """
#     Process a video by extracting frames and getting captions
    
#     Args:
#         video_path (str): Path to video file
#         markdown_file (str): Path to markdown file to update
#         gemini_api_key (str): Gemini API key
#         output_folder (str, optional): Folder to save frames
#     """
#     # Extract frames from video
#     frame_paths = extract_last_frame_per_second(video_path, output_folder)
    
#     # Process each frame
#     total_frames = len(frame_paths)
#     new_captions = 0
    
#     for i, frame_path in enumerate(frame_paths):
#         print(f"\nProcessing frame {i+1}/{total_frames}: {frame_path}")
        
#         # Get caption from Gemini
#         caption = get_caption_from_gemini(frame_path, gemini_api_key)
        
#         # Update markdown file, using Gemini for duplicate detection
#         if update_markdown(caption, markdown_file, frame_path, gemini_api_key):
#             new_captions += 1
    
#     print(f"\nSummary: Processed {total_frames} frames, added {new_captions} new captions")

# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Extract frames from video and caption them using Gemini")
#     parser.add_argument("video_path", help="Path to the input video file")
#     parser.add_argument("--output", "-o", help="Output folder for frames (optional)")
#     parser.add_argument("--markdown", "-m", default="video_captions.md", 
#                       help="Path to markdown file for captions (default: video_captions.md)")
#     parser.add_argument("--api-key", "-k", help="Gemini API key (optional, can use GEMINI_API_KEY env var)")
    
#     args = parser.parse_args()
    
#     # Get API key from args or environment
#     gemini_api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
#     if not gemini_api_key:
#         raise ValueError("Gemini API key must be provided either via --api-key argument or GEMINI_API_KEY environment variable")
    
#     process_video_frames(args.video_path, args.markdown, gemini_api_key, args.output)