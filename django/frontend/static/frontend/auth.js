const signupForm = document.querySelector("[data-signup-form]");

if (signupForm) {
  const commonPasswords = new Set([
    "password",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "admin1234",
    "butacacero",
  ]);

  const fields = {
    nombre: document.getElementById("id_nombre"),
    apellido: document.getElementById("id_apellido"),
    email: document.getElementById("id_email"),
    password1: document.getElementById("id_password1"),
    password2: document.getElementById("id_password2"),
  };

  const setError = (field, message) => {
    const target = document.querySelector(`[data-error-for="${field.id}"]`);
    if (target) {
      target.textContent = message || "";
    }
  };

  const clearServerErrors = (field) => {
    field.closest("label")?.querySelectorAll(".errorlist").forEach((errorList) => {
      errorList.remove();
    });
  };

  const normalize = (value) => value.trim().toLowerCase();

  const validate = () => {
    let isValid = true;
    const nombre = normalize(fields.nombre.value);
    const apellido = normalize(fields.apellido.value);
    const email = normalize(fields.email.value);
    const password = fields.password1.value;
    const passwordConfirm = fields.password2.value;

    setError(fields.nombre, "");
    setError(fields.apellido, "");
    setError(fields.email, "");
    setError(fields.password1, "");
    setError(fields.password2, "");

    if (nombre.length < 2) {
      setError(fields.nombre, "El nombre debe tener al menos 2 caracteres.");
      isValid = false;
    }

    if (apellido.length < 2) {
      setError(fields.apellido, "El apellido debe tener al menos 2 caracteres.");
      isValid = false;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError(fields.email, "Ingresa un email valido.");
      isValid = false;
    }

    if (password.length < 8) {
      setError(fields.password1, "La contrasena debe tener al menos 8 caracteres.");
      isValid = false;
    } else if (/^\d+$/.test(password)) {
      setError(fields.password1, "La contrasena no puede ser solo numerica.");
      isValid = false;
    } else if (commonPasswords.has(normalize(password))) {
      setError(fields.password1, "La contrasena es demasiado comun.");
      isValid = false;
    } else if (nombre && normalize(password).includes(nombre)) {
      setError(fields.password1, "La contrasena no debe parecerse al nombre.");
      isValid = false;
    } else if (apellido && normalize(password).includes(apellido)) {
      setError(fields.password1, "La contrasena no debe parecerse al apellido.");
      isValid = false;
    } else if (email && normalize(password).includes(email.split("@")[0])) {
      setError(fields.password1, "La contrasena no debe parecerse al email.");
      isValid = false;
    }

    if (passwordConfirm && password !== passwordConfirm) {
      setError(fields.password2, "Las contrasenas no coinciden.");
      isValid = false;
    }

    return isValid;
  };

  Object.values(fields).forEach((field) => {
    field.addEventListener("input", () => {
      clearServerErrors(field);
      validate();
    });
  });

  signupForm.addEventListener("submit", (event) => {
    if (!validate()) {
      event.preventDefault();
    }
  });
}
