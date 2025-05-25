# --- START OF FILE app.py ---
import streamlit as st
from PIL import Image
from rembg import remove
import io
import zipfile
import os

def convert_to_rgb_for_jpeg(image_pil):
    if image_pil.mode in ('RGBA', 'LA') or \
       (image_pil.mode == 'P' and 'transparency' in image_pil.info):
        rgb_image = Image.new("RGB", image_pil.size, (255, 255, 255))
        rgb_image.paste(image_pil, (0, 0), image_pil)
        return rgb_image
    else:
        return image_pil.convert("RGB")

def handle_file_upload_change():
    st.session_state.debug_log.append("--- handle_file_upload_change CALLED ---")
    
    # Get the current list of UploadedFile objects from the file_uploader widget
    uploaded_files_from_widget = st.session_state.get("main_file_uploader", []) # Defaults to [] if key not found or None
    
    if uploaded_files_from_widget is None: # Explicitly handle if uploader sets state to None when empty
        uploaded_files_from_widget = []
        st.session_state.debug_log.append("DEBUG CB: main_file_uploader was None, treated as [].")

    st.session_state.debug_log.append(f"DEBUG CB: main_file_uploader (from widget state) has {len(uploaded_files_from_widget)} items.")

    new_file_details = []
    if uploaded_files_from_widget:
        for i, ufo in enumerate(uploaded_files_from_widget):
            try:
                # IMPORTANT: ufo.read() consumes the file. This should ideally happen once per UploadedFile object.
                # Since this callback runs on any change, we are creating BytesIO copies.
                ufo.seek(0) # Ensure reading from the start, in case it was already touched
                content_bytes = ufo.read()
                if not content_bytes:
                    st.session_state.debug_log.append(f"DEBUG CB: File {ufo.name} (idx {i}) read empty. Already consumed or empty file?")
                new_file_details.append({
                    "name": ufo.name,
                    "content": io.BytesIO(content_bytes) # Store a fresh BytesIO copy
                })
            except Exception as e:
                st.session_state.debug_log.append(f"DEBUG CB: Could not read file {ufo.name} (idx {i}): {e}")
    else:
        st.session_state.debug_log.append("DEBUG CB: main_file_uploader is empty, so new_file_details will be empty.")
    
    st.session_state.uploaded_file_details = new_file_details
    st.session_state.debug_log.append(f"DEBUG CB: uploaded_file_details NOW has {len(st.session_state.uploaded_file_details)} items.")
    
    # If files change, any previous processing results are invalid for this new batch
    st.session_state.processed_image_data = []
    st.session_state.start_processing = False # New uploads require a new button press

def main():
    st.set_page_config(page_title="Image Background Remover", layout="wide")

    # --- Initialize Session State ---
    if "uploaded_file_details" not in st.session_state:
        st.session_state.uploaded_file_details = []
    if "processed_image_data" not in st.session_state:
        st.session_state.processed_image_data = []
    if "start_processing" not in st.session_state:
        st.session_state.start_processing = False
    if "debug_log" not in st.session_state: # For debugging
        st.session_state.debug_log = []

    st.title("📸 Image Background Remover")
    st.markdown("Upload images, click 'Remove Backgrounds', then download.")
    
    st.session_state.debug_log.append("--- Main script execution START ---")
    st.session_state.debug_log.append(f"Pre-uploader: uploaded_file_details: {len(st.session_state.uploaded_file_details)}, start_processing: {st.session_state.start_processing}, processed_data: {len(st.session_state.processed_image_data)}")
    raw_uploader_state = st.session_state.get("main_file_uploader")
    if raw_uploader_state is None:
        st.session_state.debug_log.append(f"Pre-uploader: main_file_uploader in session is None")
    else:
        st.session_state.debug_log.append(f"Pre-uploader: main_file_uploader in session has {len(raw_uploader_state)} items")


    # --- Image Upload Section ---
    st.file_uploader(
        "Choose image(s)...",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="main_file_uploader",
        on_change=handle_file_upload_change
    )

    # --- "Remove Backgrounds" Button ---
    button_visible_condition = st.session_state.uploaded_file_details and not st.session_state.processed_image_data
    st.session_state.debug_log.append(f"Button visible condition: {button_visible_condition} (uploaded_details: {bool(st.session_state.uploaded_file_details)}, not processed_data: {not st.session_state.processed_image_data})")

    if button_visible_condition:
        st.markdown("---")
        num_files_ready = len(st.session_state.uploaded_file_details)
        st.info(f"**{num_files_ready} image(s) are ready.** Click the button below to start processing.")
        
        if st.button("✨ Remove Backgrounds", type="primary", key="remove_bg_button"):
            st.session_state.debug_log.append("--- Remove Backgrounds Button CLICKED ---")
            if st.session_state.uploaded_file_details: # Check if there are files to process
                st.session_state.start_processing = True
                st.session_state.debug_log.append(f"Button Action: start_processing SET to True. Files to process: {len(st.session_state.uploaded_file_details)}")
                # No st.rerun() here, Streamlit handles rerun after button click.
            else:
                st.warning("No files currently loaded to process. Please upload files again.")
                st.session_state.start_processing = False # Ensure it's false
                st.session_state.debug_log.append("Button Action: No files in uploaded_file_details. start_processing set to False.")
            # Streamlit will rerun the script after this point.

    # --- Processing Logic ---
    st.session_state.debug_log.append(f"Pre-Processing Block: start_processing: {st.session_state.start_processing}, uploaded_details: {len(st.session_state.uploaded_file_details)}")
    if st.session_state.start_processing and st.session_state.uploaded_file_details:
        st.session_state.debug_log.append("--- Entering Processing Block ---")
        st.markdown("---")
        st.subheader("⚙️ Processing Images...")
        
        temp_processed_list = []
        files_to_process = st.session_state.uploaded_file_details # Use the list from session state
        num_to_process = len(files_to_process)

        with st.status(f"Removing backgrounds from {num_to_process} image(s)...", expanded=True) as status_ui:
            progress_bar_placeholder = st.empty() 

            for i, file_detail in enumerate(files_to_process):
                current_filename = file_detail["name"]
                status_ui.write(f"Processing: {current_filename} ({i+1}/{num_to_process})")
                try:
                    # file_detail["content"] is a BytesIO object from the callback
                    file_detail["content"].seek(0) # Reset BytesIO cursor
                    original_image = Image.open(file_detail["content"])
                    
                    processed_image = remove(original_image)
                    
                    temp_processed_list.append({
                        "original": original_image.copy(),
                        "processed": processed_image,
                        "filename": current_filename
                    })
                    st.session_state.debug_log.append(f"Processing: Successfully processed {current_filename}")
                except Exception as e:
                    st.error(f"Failed to process {current_filename}: {e}")
                    st.session_state.debug_log.append(f"Processing: FAILED for {current_filename}: {e}")
                
                progress_percentage = (i + 1) / num_to_process
                progress_bar_placeholder.progress(progress_percentage)

            st.session_state.processed_image_data = temp_processed_list
            st.session_state.start_processing = False # Reset flag after this processing batch
            st.session_state.debug_log.append(f"Processing FINISHED. Processed items: {len(temp_processed_list)}. start_processing set to False.")


            if st.session_state.processed_image_data:
                status_ui.update(label="✅ Background removal complete!", state="complete", expanded=False)
            else:
                status_ui.update(label="⚠️ No images successfully processed.", state="error", expanded=True)
    
    # --- Display Processed Results and Download Options ---
    if st.session_state.processed_image_data:
        # (Display and download logic remains the same as your previous working version)
        st.markdown("---")
        st.subheader("Processed Image Previews (Original vs. Background Removed):")
        for item in st.session_state.processed_image_data:
            st.markdown(f"#### Results for: `{item['filename']}`")
            col1, col2 = st.columns(2)
            with col1: st.image(item["original"], caption="Original Image", width=250)
            with col2: st.image(item["processed"], caption="Background Removed", width=250)
            st.markdown("---")
        st.subheader("Download Processed Image(s):")
        if len(st.session_state.processed_image_data) == 1:
            # Single download buttons
            single_item = st.session_state.processed_image_data[0]
            base_name, _ = os.path.splitext(single_item["filename"])
            png_bytes_io = io.BytesIO()
            single_item["processed"].save(png_bytes_io, format="PNG")
            st.download_button("Download as PNG", png_bytes_io.getvalue(), f"{base_name}_no_bg.png", "image/png")
            rgb_image_single = convert_to_rgb_for_jpeg(single_item["processed"])
            jpeg_bytes_io = io.BytesIO()
            rgb_image_single.save(jpeg_bytes_io, format="JPEG")
            st.download_button("Download as JPEG", jpeg_bytes_io.getvalue(), f"{base_name}_no_bg.jpeg", "image/jpeg")
        else: # Multiple images
            # PNG ZIP
            png_zip_buffer = io.BytesIO()
            with zipfile.ZipFile(png_zip_buffer, "w") as png_zip:
                for item in st.session_state.processed_image_data:
                    base_name, _ = os.path.splitext(item["filename"])
                    img_arr = io.BytesIO()
                    item["processed"].save(img_arr, format="PNG")
                    png_zip.writestr(f"{base_name}_no_bg.png", img_arr.getvalue())
            st.download_button("Download All as PNG (ZIP)", png_zip_buffer.getvalue(), "images_no_bg_png.zip", "application/zip")
            # JPEG ZIP
            jpeg_zip_buffer = io.BytesIO()
            with zipfile.ZipFile(jpeg_zip_buffer, "w") as jpeg_zip:
                for item in st.session_state.processed_image_data:
                    base_name, _ = os.path.splitext(item["filename"])
                    rgb_img = convert_to_rgb_for_jpeg(item["processed"])
                    img_arr = io.BytesIO()
                    rgb_img.save(img_arr, format="JPEG")
                    jpeg_zip.writestr(f"{base_name}_no_bg.jpeg", img_arr.getvalue())
            st.download_button("Download All as JPEG (ZIP)", jpeg_zip_buffer.getvalue(), "images_no_bg_jpeg.zip", "application/zip")


    # --- Footer / Initial Message ---
    if not st.session_state.uploaded_file_details and not st.session_state.processed_image_data:
        st.markdown("---")
        st.info("👋 Please upload one or more image files to get started!")
    
    st.markdown("---")
    st.markdown("Built with ❤️ using Streamlit and `rembg`.")

    # --- Debug Log Display ---
    with st.expander("Debug Log", expanded=False):
        for entry in st.session_state.debug_log:
            st.text(entry)
        if st.button("Clear Debug Log"):
            st.session_state.debug_log = []
            st.rerun()

if __name__ == "__main__":
    main()
# --- END OF FILE app.py ---