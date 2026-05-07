import { render, screen, fireEvent } from "@testing-library/react";
import EarlyAccessModal from "../EarlyAccessModal";

const baseFormData = {
  firstName: "",
  lastName: "",
  email: "",
  phone: "",
  preferredContact: "email",
  careerJourney: "",
};

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  isSuccess: false,
  onDismissSuccess: vi.fn(),
  formData: baseFormData,
  onChange: vi.fn(),
  isSubmitting: false,
  error: "",
  onSubmit: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EarlyAccessModal - visibility", () => {
  it("renders nothing when isOpen is false", () => {
    render(<EarlyAccessModal {...defaultProps} isOpen={false} />);
    expect(screen.queryByText("Tell us how you want to connect")).toBeNull();
  });

  it("renders the form when isOpen is true", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    expect(screen.getByText("Tell us how you want to connect")).toBeInTheDocument();
  });

  it("does not show the success overlay when isSuccess is false", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    expect(screen.queryByText("Request received!")).toBeNull();
  });

  it("shows the success overlay when isSuccess is true", () => {
    render(<EarlyAccessModal {...defaultProps} isOpen={false} isSuccess={true} />);
    expect(screen.getByText("Request received!")).toBeInTheDocument();
  });

  it("can show both the form and success overlay simultaneously", () => {
    render(<EarlyAccessModal {...defaultProps} isOpen={true} isSuccess={true} />);
    expect(screen.getByText("Tell us how you want to connect")).toBeInTheDocument();
    expect(screen.getByText("Request received!")).toBeInTheDocument();
  });
});

describe("EarlyAccessModal - closing", () => {
  it("calls onClose when the X button is clicked", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.click(screen.getByLabelText("Close modal"));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the Cancel button is clicked", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.click(document.querySelector('[aria-hidden="true"]')!);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onDismissSuccess when success close button is clicked", () => {
    render(<EarlyAccessModal {...defaultProps} isOpen={false} isSuccess={true} />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(defaultProps.onDismissSuccess).toHaveBeenCalledTimes(1);
  });
});

describe("EarlyAccessModal - form submission", () => {
  it("calls onSubmit when the Send request button is clicked", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(defaultProps.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("shows Sending... and disables the button while submitting", () => {
    render(<EarlyAccessModal {...defaultProps} isSubmitting={true} />);
    const btn = screen.getByRole("button", { name: "Sending..." });
    expect(btn).toBeDisabled();
  });

  it("shows the error message when error is set", () => {
    render(<EarlyAccessModal {...defaultProps} error="Something went wrong" />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("does not show an error message when error is empty", () => {
    render(<EarlyAccessModal {...defaultProps} error="" />);
    expect(screen.queryByText(/went wrong/i)).toBeNull();
  });
});

describe("EarlyAccessModal - input interactions", () => {
  it("calls onChange with field and value when first name is typed", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.change(screen.getByPlaceholderText("Your first name"), {
      target: { value: "Ada" },
    });
    expect(defaultProps.onChange).toHaveBeenCalledWith("firstName", "Ada");
  });

  it("calls onChange with field and value when email is typed", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "ada@example.com" },
    });
    expect(defaultProps.onChange).toHaveBeenCalledWith("email", "ada@example.com");
  });

  it("calls onChange when a preferred contact radio is selected", () => {
    render(<EarlyAccessModal {...defaultProps} />);
    fireEvent.click(screen.getByRole("radio", { name: "Text" }));
    expect(defaultProps.onChange).toHaveBeenCalledWith("preferredContact", "text");
  });

  it("calls onChange when career journey textarea is typed", () => {
    render(
      <EarlyAccessModal
        {...defaultProps}
        formData={{ ...baseFormData, careerJourney: "" }}
      />
    );
    fireEvent.change(
      screen.getByPlaceholderText(/Share your path/i),
      { target: { value: "I've been in tech for 5 years." } }
    );
    expect(defaultProps.onChange).toHaveBeenCalledWith(
      "careerJourney",
      "I've been in tech for 5 years."
    );
  });
});
