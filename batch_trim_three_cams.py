import csv
import subprocess
import os
import json
import re

# --- Configuration (Keep these the same) ---
INPUT_CSV_FILE = 'trim_list_Dec9.csv'
OUTPUT_FOLDER = '/Users/kristensteudel/Library/CloudStorage/GoogleDrive-steudelk@stanford.edu/My Drive/NMBL/Stanford Football OpenCap Screening/Sony Camera Calibration Videos /Testing December 9/Trimmed Videos/'
FFMPEG_PATH = 'ffmpeg'
# ---

def get_video_fps(input_file):
    """
    Detects the frames per second (FPS) of a video using ffprobe.
    Returns: FPS as a float, or None if detection fails.
    """
    try:
        # Ask ffprobe for full stream info in JSON so we can pick the most reliable fields
        command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'v:0',
            input_file
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        streams = info.get('streams', [])
        if not streams:
            return None
        stream = streams[0]

        def parse_frac(frac_str):
            try:
                if not frac_str or frac_str == '0/0':
                    return None
                if '/' in frac_str:
                    num, den = frac_str.split('/')
                    return float(num) / float(den)
                return float(frac_str)
            except Exception:
                return None

        # Prefer avg_frame_rate, fall back to r_frame_rate
        for key in ('avg_frame_rate', 'r_frame_rate'):
            if key in stream:
                v = parse_frac(stream.get(key))
                if v and v > 0:
                    return v

        # If the above aren't usable, compute from nb_frames/duration
        nb_frames = stream.get('nb_frames')
        duration = stream.get('duration') or stream.get('duration_ts')
        try:
            if nb_frames and duration:
                fps = float(nb_frames) / float(duration)
                if fps > 0:
                    return fps
        except Exception:
            pass

        return None
    except Exception as e:
        print(f"WARNING: Could not detect FPS for {input_file}: {e}")
        return None

def run_ffmpeg_command(input_file, start_frame, frame_count, output_file, fps=None):
    """
    Constructs and runs the FFmpeg command for precise frame-number trimming.
    
    Uses -ss (seek) and -vf fps filter to trim the video properly without black padding.
    The output will be re-encoded using H.264 (libx264) for cross-compatibility.
    
    Args:
        input_file: Path to input video
        start_frame: Starting frame number
        frame_count: Number of frames to extract
        output_file: Path to output video
        fps: Frames per second (auto-detected if None)
    """
    
    # Auto-detect FPS if not provided
    if fps is None:
        fps = get_video_fps(input_file)
        if fps is None:
            print(f"WARNING: Using default 30 fps for {input_file}")
            fps = 30.0
    
    # Convert frame numbers to seconds
    start_frame = int(start_frame)
    frame_count = int(frame_count)

    start_time = start_frame / fps
    # duration in seconds for the requested number of frames
    duration = frame_count / fps

    # Use -ss after -i for accurate (frame-accurate) seeking.
    # Use -frames:v to extract an exact number of frames rather than relying on duration.
    command = [
        FFMPEG_PATH,
        '-y',               # Overwrite output files without asking
        '-i', input_file,
        '-ss', f'{start_time:.6f}',  # Accurate seek (slower but frame-accurate)
        '-frames:v', str(frame_count),  # Extract exact number of frames

        # 3. Codec for Output (H.264 High Quality)
        '-c:v', 'libx264',
        '-crf', '18',       # Quality setting: lower number = higher quality/larger file

        # 4. Audio encoding
        '-c:a', 'aac',
        '-b:a', '128k',

        output_file
    ]

    print(f"\nProcessing: {os.path.basename(input_file)}")
    print(f"  Frames {start_frame}-{start_frame + frame_count} ({frame_count} frames)")
    print(f"  Time range: {start_time:.6f}s to {start_time + duration:.6f}s (FPS: {fps})")
    print(f"  Output: {output_file}")
    
    try:
        # Execute the command
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"  ✓ SUCCESS: Trimmed video saved")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ ERROR: Failed to process {input_file}")
        print(f"  FFmpeg output:\n{e.stderr}")
    except FileNotFoundError:
        print(f"  ✗ ERROR: FFmpeg not found at '{FFMPEG_PATH}'. Please check your FFMPEG_PATH setting.")



def process_batch():
    """
    Reads the CSV and iterates through the videos, trimming each triplet of cameras.
    
    CSV Format:
    Cam 1 File Location,Camera 1 Input File,Cam 2 File Location,Camera 2 Input File,Cam 3 File Location,Camera 3 Input File,Start Frame,Frame Count,[Start Frame 2],[Frame Count 2],...
    
    You can add more columns for additional clips from the same source video.
    """
    
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"Created output directory: {OUTPUT_FOLDER}\n")
        
    try:
        with open(INPUT_CSV_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            
            # Skip the header row
            header = next(reader)
            print(f"--- Starting Batch Process ---")
            print(f"Header: {header}\n")
            
            for row_num, row in enumerate(reader, start=2):
                if not row or all(cell.strip() == '' for cell in row):
                    continue
                
                # Ensure we have at least the basic 8 columns (6 for paths/filenames + 2 for frame info)
                if len(row) < 8:
                    print(f"WARNING: Row {row_num} has fewer than 8 columns. Skipping.")
                    continue
                
                # Extract base information (first 6 columns are paths/filenames for 3 cameras)
                cam1_file_location = row[0].strip()
                cam1_in = row[1].strip()
                cam2_file_location = row[2].strip()
                cam2_in = row[3].strip()
                cam3_file_location = row[4].strip()
                cam3_in = row[5].strip()
                
                # Build full paths
                input_path_1 = cam1_file_location + cam1_in
                input_path_2 = cam2_file_location + cam2_in
                input_path_3 = cam3_file_location + cam3_in
                
                # Get FPS for all three cameras (should be the same, but detect independently)
                fps_1 = get_video_fps(input_path_1)
                fps_2 = get_video_fps(input_path_2)
                fps_3 = get_video_fps(input_path_3)
                
                # Process all trim ranges for this video triplet
                # Columns 6+ come in pairs: (Start Frame, Frame Count)
                trim_index = 1
                for i in range(6, len(row), 2):
                    if i + 1 >= len(row):
                        break
                    
                    start_frame_str = row[i].strip()
                    frame_count_str = row[i + 1].strip()
                    
                    # Skip if either is empty
                    if not start_frame_str or not frame_count_str:
                        continue
                    
                    try:
                        start_frame = int(start_frame_str)
                        frame_count = int(frame_count_str)
                    except ValueError:
                        print(f"WARNING: Row {row_num}, columns {i+1}-{i+2}: Invalid frame numbers. Skipping.")
                        continue
                    
                    print(f"\n{'='*70}")
                    print(f"Row {row_num}, Trim Set {trim_index}: {os.path.basename(cam1_in)} & {os.path.basename(cam2_in)} & {os.path.basename(cam3_in)}")
                    print(f"{'='*70}")
                    
                    # --- Trim Camera 1 ---
                    if trim_index == 1:
                        output_name_1 = f"FRAME_TRIM_{cam1_in}"
                    else:
                        # Add clip number for multiple clips from same source
                        name_parts = cam1_in.rsplit('.', 1)
                        output_name_1 = f"FRAME_TRIM_{name_parts[0]}_clip{trim_index}.{name_parts[1]}"
                    
                    output_path_1 = os.path.join(OUTPUT_FOLDER, output_name_1)
                    run_ffmpeg_command(input_path_1, start_frame, frame_count, output_path_1, fps_1)
                    
                    # --- Trim Camera 2 ---
                    if trim_index == 1:
                        output_name_2 = f"FRAME_TRIM_{cam2_in}"
                    else:
                        name_parts = cam2_in.rsplit('.', 1)
                        output_name_2 = f"FRAME_TRIM_{name_parts[0]}_clip{trim_index}.{name_parts[1]}"
                    
                    output_path_2 = os.path.join(OUTPUT_FOLDER, output_name_2)
                    run_ffmpeg_command(input_path_2, start_frame, frame_count, output_path_2, fps_2)
                    
                    # --- Trim Camera 3 ---
                    if trim_index == 1:
                        output_name_3 = f"FRAME_TRIM_{cam3_in}"
                    else:
                        name_parts = cam3_in.rsplit('.', 1)
                        output_name_3 = f"FRAME_TRIM_{name_parts[0]}_clip{trim_index}.{name_parts[1]}"
                    
                    output_path_3 = os.path.join(OUTPUT_FOLDER, output_name_3)
                    run_ffmpeg_command(input_path_3, start_frame, frame_count, output_path_3, fps_3)
                    
                    trim_index += 1

    except ValueError as e:
        print(f"\nERROR: CSV parsing error: {e}")
    except FileNotFoundError:
        print(f"FATAL ERROR: Input CSV file '{INPUT_CSV_FILE}' not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    process_batch()