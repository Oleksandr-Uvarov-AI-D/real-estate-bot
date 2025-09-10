const submitButton =  document.getElementById("submit_button");



submitButton.addEventListener(("click"), async () => {
    const email = document.querySelector('input[name="email"]').value;
    const firstName = document.querySelector('textarea[name="first_name"]').value;
    const lastName = document.querySelector('textarea[name="last_name"]').value;
    const phoneNumber = document.querySelector('textarea[name="phone_number"]').value;

    // const response = await fetch("https://real-estate-bot-4dxy.onrender.com/formspree", {
    const response = await fetch("http://127.0.0.1:8000/formspree", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({"firstName": firstName, "lastName": lastName, "email": email, "phone": phoneNumber})});

    });

