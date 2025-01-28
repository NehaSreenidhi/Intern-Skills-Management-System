import bcrypt
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify
import pymongo
import os
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np


app = Flask(__name__)
# secret key for the session
app.secret_key = os.urandom(24)

# Loading SentenceTransformer model
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# MongoDB conncetion
myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["myDBase"]
mycol = mydb["interns"]
mentCol = mydb["mentors"]

# FAISS Setup
index = faiss.IndexFlatL2(384) 
model = SentenceTransformer('all-MiniLM-L6-v2')
dimension = 384
interns_metadata = []

def populate_faiss():
    # Retrieve skills from MongoDB and generate embeddings
    interns = mycol.find()  # Retrieve all interns (or filter as needed)
    embeddings = []
    ids = []

    for intern in interns:
        for skill in intern.get("skills", []):
            skill_name = skill.get("skill_name", "")
            skill_vector = model.encode([skill_name])[0]
            embeddings.append(skill_vector)
            ids.append(intern.get("email", ""))

    # Convert embeddings list to numpy array
    embeddings = np.array(embeddings).astype('float32')

    # Ensure embeddings are the correct dimension
    if embeddings.shape[1] != 384:
        raise ValueError(f"Expected embeddings with dimension 384, but got {embeddings.shape[1]}")

    # Add embeddings to FAISS index
    index.add(embeddings)

populate_faiss()

@app.route("/")
def home():
    if "user" in session:
        return f"Welcome, {session['user']}!"
    return render_template("landingPage.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        name = request.form["name"]

        if mycol.find_one({"email": email}):
            flash("Email already registered. Please log in.", "warning")
            return redirect("/register")
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        try:
            mycol.insert_one({"email": email, "password": hashed_password, "name":name})
            flash("Registration successful! You can now log in.", "success")
            return redirect("/login")  
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")
            return redirect("/register")
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('userType')

        if user_type == 'Intern':
            user = mycol.find_one({"email": email})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
                session['email'] = email  # Store email in session
                session['user_type'] = user_type  # Store user type in session
                return redirect(url_for('intern_dashboard'))  

        elif user_type == 'Mentor':
            mentor = mentCol.find_one({"email": email})
            if mentor and password == mentor['password']:
                session['email'] = email  # Store email in session
                session['user_type'] = 'Mentor'  # Store user type in session
                return redirect(url_for('mentor_dashboard'))  

        flash('Invalid credentials. Please try again.', 'danger')
        return redirect(url_for('login')) 
    return render_template('login.html')  

@app.route('/intern_dashboard')
def intern_dashboard():
    if "email" not in session:
        return redirect("/login")
    
    user_email = session["email"]
    user = mycol.find_one({"email": user_email})
    if user and "name" in user:
        name = user["name"]
    else:
        name = "Intern"  

    return render_template("intern_dashboard.html", name=name)

# (Working - regular mongo query)
# @app.route("/add_skills", methods=["POST"])
# def add_skills():
#     if "email" not in session or session["user_type"] != "Intern":
#         return redirect("/login")

#     # Fetching the skill details from the form
#     skill_name = request.form["skillName"]
#     skill_level = request.form["skillLevel"]
#     email = session["email"]

#     # Fetching the intern's profile
#     intern = mycol.find_one({"email": email})
#     if not intern:
#         flash("Intern profile not found.", "danger")
#         return redirect("/intern_dashboard")

#     # Fetching the current skills list
#     updated_skills = intern.get("skills", [])

#     # Checking for duplicate skill
#     if any(skill["skill_name"].lower() == skill_name.lower() for skill in updated_skills):
#         flash(f"The skill '{skill_name}' already exists in your profile.", "warning")
#         return redirect("/intern_dashboard")
    
#     # Creating embedding for the new skill name
#     skill_embedding = model.encode([skill_name])[0]  # Encoding the skill name

#     # Adding the new skill to the list
#     updated_skills.append({"skill_name": skill_name, "skill_level": skill_level})

#     # Updating the database
#     try:
#         mycol.update_one({"email": email}, {"$set": {"skills": updated_skills}}, upsert=False)

#         # Adding the skill's embedding to FAISS index
#         faiss_index.add(np.array([skill_embedding], dtype=np.float32)) 

#         flash(f"Skill '{skill_name}' added successfully!", "success")
#     except Exception as e:
#         flash(f"Error updating MongoDB: {str(e)}", "danger")
#         return redirect("/intern_dashboard")

#     return redirect("/intern_dashboard")

@app.route("/add_skills", methods=["POST"])
def add_skills():
    if "email" not in session or session["user_type"] != "Intern":
        return redirect("/login")

    # Fetching the skill details from the form
    skill_name = request.form["skillName"]
    skill_level = request.form["skillLevel"]
    email = session["email"]

    # Fetching the intern's profile
    intern = mycol.find_one({"email": email})
    if not intern:
        flash("Intern profile not found.", "danger")
        return redirect("/intern_dashboard")

    # Fetching the current skills list
    updated_skills = intern.get("skills", [])

    # Checking for duplicate skill
    if any(skill["skill_name"].lower() == skill_name.lower() for skill in updated_skills):
        flash(f"The skill '{skill_name}' already exists in your profile.", "warning")
        return redirect("/intern_dashboard")
    
    # Creating embedding for the new skill name
    skill_embedding = model.encode([skill_name])[0]  # Encoding the skill name

    # Adding the new skill to the list
    updated_skills.append({"skill_name": skill_name, "skill_level": skill_level})

    # Updating the database
    try:
        mycol.update_one({"email": email}, {"$set": {"skills": updated_skills}}, upsert=False)

        # Adding the skill's embedding to FAISS index
        index.add(np.array([skill_embedding], dtype=np.float32)) 

        flash(f"Skill '{skill_name}' added successfully!", "success")
    except Exception as e:
        flash(f"Error updating MongoDB: {str(e)}", "danger")
        return redirect("/intern_dashboard")

    return redirect("/intern_dashboard")

@app.route('/get_skills', methods=["GET"])
def get_skills():
    if "email" not in session or session["user_type"] != "Intern":
        return jsonify({"error": "Unauthorized access"}), 401

    # logged-in intern's email - from the session
    email = session["email"]

    # MongoDB Query - retrieve the the skills field of intern
    intern = mycol.find_one({"email": email}, {"_id": 0, "skills": 1})
    if not intern:
        return jsonify({"error": "Intern profile not found"}), 404
    skillsList = intern.get("skills", [])

    # Returning the skills as a JSON response
    return jsonify({"skills": skillsList}), 200

@app.route('/mentor_dashboard')
def mentor_dashboard():
    if "email" not in session:  
        return redirect("/login")
    user_email = session["email"]
    user = mentCol.find_one({"email": user_email})
    if user and "name" in user:
        name = user["name"]
    else:
        name = "Mentor"  
    return render_template('mentor_dashboard.html', name=name)

@app.route('/check_interns')
def check_interns():
    if "email" not in session: 
        return redirect("/login")
    user_email = session["email"]
    user = mentCol.find_one({"email": user_email})
    if user and "name" in user:
        name = user["name"]
    else:
        name = "Mentor" 
    ints = mycol.find()
    interns_list = list(ints)
    return render_template('check_interns.html', interns_list=interns_list, name = name)

# (Working - regular mongo query)
# @app.route('/search_interns', methods=["GET", "POST"])
# def search_interns():
#     if "email" not in session:  
#         return redirect("/login")

#     user_email = session["email"]
#     user = mentCol.find_one({"email": user_email})
#     name = user["name"] if user and "name" in user else "Mentor"
    
#     search_results = [] 

#     if request.method == "POST":
#         search_query = request.form.get("searchQuery", "").strip()

#         # if search_query:
#         #     # Mongo Query
#         #     interns = mycol.find({"skills.skill_name": {"$regex": search_query, "$options": "i"}})

#         #     # Collecting matching intern profiles
#         #     for intern in interns:
#         #         intern_data = {
#         #             "name": intern.get("name", "Unknown"),
#         #             "email": intern.get("email", ""),
#         #             "skills": intern.get("skills", [])
#         #         }
#         #         search_results.append(intern_data)
#         if search_query:
#             # Perform FAISS similarity search for query
#             query_vector = model.encode([search_query])[0]
#             query_vector = np.array([query_vector]).astype('float32')
            
#             # Search in FAISS index
#             D, I = index.search(query_vector, k=5)  # k is the number of nearest neighbors to retrieve
            
#             # Process the results
#             search_results = []
#             for i in range(len(I[0])):
#                 if I[0][i] != -1:
#                     intern_email = ids[I[0][i]]  # Get intern email from stored IDs
#                     intern = mycol.find_one({"email": intern_email})
#                     intern_data = {
#                         "name": intern.get("name", "Unknown"),
#                         "email": intern.get("email", ""),
#                         "skills": intern.get("skills", [])
#                     }
#                     search_results.append(intern_data)

#     print(f"Search results: {search_results}")  # Debugging the results
#     return render_template("search_interns.html", name=name, search_results=search_results)

@app.route('/search_interns', methods=["GET", "POST"])
def search_interns():
    if "email" not in session:  
        return redirect("/login")

    user_email = session["email"]
    user = mycol.find_one({"email": user_email})
    name = user["name"] if user and "name" in user else "Mentor"
    
    search_results = [] 

    if request.method == "POST":
        search_query = request.form.get("searchQuery", "").strip()

        if search_query:
            # Perform the search query for intern skills using FAISS
            # Generate embedding for the search query
            query_vector = model.encode([search_query])[0].astype('float32').reshape(1, -1)
            # Perform similarity search in FAISS index
            D, I = index.search(query_vector, k=10)  # Top 10 results
            # Collect matching intern profiles from MongoDB
            results = list(mycol.find())
            num_results = len(results)  # Number of results in MongoDB
            print(I[0])
            for idx in I[0]:  # idx is the index of the matched result in the FAISS index
                
                if 0 <= idx < num_results:  # Ensure idx is within valid range
                    intern_email = results[idx]["email"]
                    intern = mycol.find_one({"email": intern_email})
                    if intern:  # Check if intern is not None
                        intern_data = {
                            "name": intern.get("name", "Unknown"),
                            "email": intern.get("email", ""),
                            "skills": intern.get("skills", [])
                        }
                        search_results.append(intern_data)
                else:
                    print(f"Index {idx} is out of range.")

    return render_template("search_interns.html", name=name, search_results=search_results)


@app.route("/logout")
def logout():
    session.clear() 
    flash("You have been logged out.", "info")
    return redirect("/login") 

if __name__ == "__main__":
    app.run(debug=True)
