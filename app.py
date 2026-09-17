import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv
import os
import math
import pandas as pd

load_dotenv() # make sure environment variables are loaded into our script
# Retrieve Supabase URL
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

def sign_up(email, password):
    try:
        user = supabase.auth.sign_up({"email": email, "password": password})
        return user
    except Exception as e:
        st.error(f"Registration failed: {e}")

def sign_in(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password}) 
        if res.session:
            st.session_state.access_token = res.session.access_token
            st.session_state.user_email = res.user.email
        return res
    except Exception as e:
        st.error(f"Login failed: {e}")    

def sign_out():
    try:
        supabase.auth.sign_out()
        st.session_state.user_email = None
        st.rerun()
    except Exception as e:
        st.error(f"Logout failed: {e}") 

def get_authenticated_client():
    token = st.session_state.get("access_token")
    if token:
        # Pass the access token so RLS recognizes the logged-in user
        supabase.postgrest.auth(token)
        return supabase
        #return create_client(supabase_url, supabase_key, options=ClientOptions(headers={"Authorization": f"Bearer {token}"}))
    return supabase


def load_user_data(user_email):
    # Fetch student data assigned to user
    client = get_authenticated_client()
    response = client.table("mile_records").select("*").eq("user_email", user_email).execute()
    data = response.data

    # Process DB rows back into nested dictionary structure
    students = {}
    for row in data:
        name = row["student_name"]
        if name not in students:
            students[name] = {}
        if row["run_number"] and row["mile_time"]:
            students[name][row["run_number"]] = row["mile_time"]

    return students

def main_app(user_email):
    st.title("👟 P.E. Mile Tracking System")
    st.success(f"Welcome, {user_email}! 🎉")

    tab1, tab2, tab3 = st.tabs(["📊 Class Overview", "👤 Individual Student", "➕ Add Data"])

    with tab1:
        st.header("Class-Wide Performance")
        all_times = []
        max_runs = 0
        for s_dict in st.session_state.students.values():
            all_times.extend(s_dict.values())
            if s_dict:
                max_run_in_student = max(s_dict.keys())
                if max_run_in_student > max_runs:
                    max_runs = max_run_in_student

        if all_times:
            all_seconds = convert_to_seconds(all_times)
            avg_sec = math.ceil(sum(all_seconds) / len(all_seconds))
            fastest_sec = min(all_seconds)
            slowest_sec = max(all_seconds)
            passing_pct = (sum(1 for s in all_seconds if s <= 600) / len(all_seconds)) * 100

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Class Average", convert_to_min_and_sec(avg_sec))
            col2.metric("Fastest Time", convert_to_min_and_sec(fastest_sec))
            col3.metric("Slowest Time", convert_to_min_and_sec(slowest_sec))
            col4.metric("% Passing (<=10:00)", f"{passing_pct:.1f}%")

            # Prepare line chart data: Average time per Run Attempt across all students
            run_data = {}
            for run_number in range(1, max_runs + 1):
                run_seconds = []
                for s_dict in st.session_state.students.values():
                    if run_number <= len(s_dict):
                        run_seconds.append(convert_to_seconds([s_dict[run_number]])[0])
                if run_seconds:
                    run_data[f"Run {run_number}"] = sum(run_seconds) / len(run_seconds) / 60  # convert to decimal mins for plotting
            if run_data:  
                df_class = pd.DataFrame(list(run_data.items()), columns=["Run Attempt", "Average Minutes"])
                st.subheader("Class Progress Over Time (Average Minutes)")
                st.line_chart(df_class.set_index("Run Attempt"))

    with tab2:
        st.header("Student Progress")
        selected_student = st.selectbox("Select Student", list(st.session_state.students.keys()))

        if selected_student:
            student_runs = st.session_state.students[selected_student]
            if student_runs:
                run_numbers = sorted(student_runs.keys())
                times = [student_runs[i] for i in run_numbers] # list of times
                sec_list = convert_to_seconds(times)

                # Metrics
                c1, c2, c3 = st.columns(3)
                c1.metric("Average", convert_to_min_and_sec(math.ceil(sum(sec_list) / len(sec_list))))
                c2.metric("Fastest", convert_to_min_and_sec(min(sec_list)))
                c3.metric("Slowest", convert_to_min_and_sec(max(sec_list)))

                # Line graph
                df_ind = pd.DataFrame({
                    "Run Attempt": [f"Run {i}" for i in run_numbers],
                    "Time (Minutes)": [s / 60 for s in sec_list]
                })
                st.subheader(f"{selected_student}'s Progress Chart")
                st.line_chart(df_ind.set_index("Run Attempt"))

                # Format raw recorded times from dictionary (e.g., Run 1: 7:30, Run 2: 8:00)
                formatted_raw_times = ", ".join([f"Run {r}: {student_runs[r]}" for r in run_numbers])
                st.write("**Raw Recorded Times:**", formatted_raw_times)
                
            else:
                st.info(f"No mile times recorded yet for {selected_student}.")

    with tab3:
        st.header("Manage Roster and Times")
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Update Student List")
            new_name = st.text_input("Student Name")
            if st.button("Add Student"):
                if new_name and new_name not in st.session_state.students:
                    try:
                        client = get_authenticated_client()
                        client.table("mile_records").insert({
                            "user_email": st.session_state.user_email,
                            "student_name": new_name,
                            "run_number": None,
                            "mile_time": None
                        }).execute()
                        st.session_state.students[new_name] = {}
                        st.success(f"Added {new_name} to roster.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add student {e}")
                elif new_name in st.session_state.students:
                    st.warning("Student already exists.")
            if st.button("Remove Student"):
                if len(st.session_state.students) == 1:
                    st.warning("Cannot remove student; a class needs at least one!")
                elif new_name and new_name in st.session_state.students:
                    try:
                        client = get_authenticated_client()
                        client.table("mile_records") \
                            .delete() \
                            .eq("user_email", st.session_state.user_email) \
                            .eq("student_name", new_name) \
                            .execute()
                        del st.session_state.students[new_name]
                        st.success(f"Removed {new_name} from roster.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to remove student: {e}")
                elif new_name not in st.session_state.students:
                    st.warning("Student is not on the roster.")

        with col_b:
            st.subheader("Log Mile Time")
            student_target = st.selectbox("Select Student to Update", list(st.session_state.students.keys()))

            # Pick an existing run number or the next run
            student_times = st.session_state.students[student_target]
            mile_number = st.number_input(
                "Run Number", 
                min_value=1, 
                max_value=max(len(student_times) + 1, 1), 
                value=len(student_times) + 1
            )
            mins = st.number_input("Minutes", min_value=0, max_value=59, value=8)
            secs = st.number_input("Seconds", min_value=0, max_value=59, value=30)

            if st.button("Save Mile Time"):
                formatted_time = f"{mins}:{secs:02d}"

                try:
                    # 1. Use the authenticated client to bypass/satisfy RLS
                    client = get_authenticated_client()
                    client.table("mile_records").upsert({
                        "user_email": user_email,
                        "student_name": student_target,
                        "run_number": mile_number,
                        "mile_time": formatted_time
                    },
                    on_conflict="user_email, student_name, run_number"
                    ).execute()

                    # 2. Update local state so UI updates immediately
                    if student_target not in st.session_state.students:
                        st.session_state.students[student_target] = {}
                    st.session_state.students[student_target][mile_number] = formatted_time

                    st.success(f"Saved Run #{mile_number} as {formatted_time} for {student_target}!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to save mile time {e}")


    if st.button("Logout"):
        sign_out()

def auth_screen():
    st.title("👟 P.E. Mile Tracking System")
    option = st.selectbox("Choose an action:", ["Login", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if option == "Sign Up" and st.button("Register"):
        user = sign_up(email, password)
        if user and user.user:
            st.success("Registration successful! Please log in.")

    if option == "Login" and st.button("Login"):
        user = sign_in(email, password)
        if user and user.user:
            st.session_state.user_email = user.user.email
            st.success(f"Welcome back, {email}!")
            st.rerun()

if "students" not in st.session_state:
    st.session_state.students = {
        "Student A": {1: "7:30", 2: "8:00", 3: "7:02"},
        "Student B": {1: "12:20", 2: "9:33", 3: "10:54"}
    }

# Helper Functions
def convert_to_seconds(mile_time_list):
    mile_time_list_in_seconds = []
    for mile_time in mile_time_list:
        split_mile_time = mile_time.split(":")
        mile_time_in_seconds = (int(split_mile_time[0]) * 60) + int(split_mile_time[1])
        mile_time_list_in_seconds.append(mile_time_in_seconds)
    return mile_time_list_in_seconds

# After finding the fastest, slowest, or average mile time, this function is used to turn the integer back into a min:sec format
def convert_to_min_and_sec(mile_time_in_seconds: int) -> str:
    min = mile_time_in_seconds // 60
    sec = mile_time_in_seconds % 60
    if sec < 10:
        sec = "0" + str(sec)
    final_mile_time = str(min) + ":" + str(sec)
    return final_mile_time


st.set_page_config(page_title="P.E. Mile Tracker", page_icon="👟", layout="wide")

# does user_email exist in the session state
if "user_email" not in st.session_state:
    st.session_state.user_email = None

if st.session_state.user_email:
    main_app(st.session_state.user_email)
else:
    auth_screen()