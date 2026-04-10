/** Fallback metadata for face wizard controls — mirrors app.py `FACE_REF_*` (used if API fails). */

export type FaceRefOption = { value: string; label: string };

export type FaceRefOptionsPayload = {
	defaults: Record<string, string>;
	fields: Record<string, FaceRefOption[]>;
};

export const FACE_REF_OPTIONS_STATIC: FaceRefOptionsPayload = {
	defaults: {
		sex: 'female',
		ethnicity: 'unspecified',
		age: 'young_adult',
		hair_color: 'brown',
		hair_length: 'medium',
		eye_color: 'brown',
		facial_hair: 'none',
		image_style: 'anime',
	},
	fields: {
		image_style: [
			{ value: 'anime', label: 'Anime / cel-shaded' },
			{ value: 'semi_realistic', label: 'Semi-realistic illustration' },
			{ value: 'soft_anime', label: 'Soft anime / VN' },
			{ value: 'realistic', label: 'Photorealistic' },
			{ value: 'painterly', label: 'Painterly / digital paint' },
			{ value: 'comic', label: 'Comic / graphic novel' },
			{ value: 'watercolor', label: 'Watercolor style' },
		],
		sex: [
			{ value: 'unspecified', label: 'Unspecified' },
			{ value: 'female', label: 'Female' },
			{ value: 'male', label: 'Male' },
			{ value: 'androgynous', label: 'Androgynous' },
		],
		ethnicity: [
			{ value: 'unspecified', label: 'Unspecified' },
			{ value: 'east_asian', label: 'East Asian' },
			{ value: 'south_asian', label: 'South Asian' },
			{ value: 'southeast_asian', label: 'Southeast Asian' },
			{ value: 'black', label: 'Black / African' },
			{ value: 'white_european', label: 'White / European' },
			{ value: 'middle_eastern', label: 'Middle Eastern' },
			{ value: 'latino', label: 'Latino / Hispanic' },
			{ value: 'pacific', label: 'Pacific Islander' },
			{ value: 'indigenous', label: 'Indigenous' },
			{ value: 'mixed', label: 'Mixed' },
		],
		age: [
			{ value: 'unspecified', label: 'Unspecified' },
			{ value: 'teen', label: 'Teen' },
			{ value: 'young_adult', label: 'Young adult' },
			{ value: 'adult', label: 'Adult' },
			{ value: 'middle_aged', label: 'Middle-aged' },
			{ value: 'senior', label: 'Senior' },
		],
		hair_color: [
			{ value: 'black', label: 'Black' },
			{ value: 'brown', label: 'Brown' },
			{ value: 'blonde', label: 'Blonde' },
			{ value: 'red', label: 'Red / ginger' },
			{ value: 'auburn', label: 'Auburn' },
			{ value: 'gray_white', label: 'Gray / white' },
			{ value: 'silver', label: 'Silver' },
			{ value: 'platinum', label: 'Platinum blonde' },
			{ value: 'blue', label: 'Blue (dyed)' },
			{ value: 'green', label: 'Green (dyed)' },
			{ value: 'pink', label: 'Pink (dyed)' },
			{ value: 'purple', label: 'Purple (dyed)' },
			{ value: 'multicolor', label: 'Multicolor' },
		],
		hair_length: [
			{ value: 'bald', label: 'Bald' },
			{ value: 'buzz', label: 'Buzz cut' },
			{ value: 'short', label: 'Short' },
			{ value: 'medium', label: 'Medium' },
			{ value: 'long', label: 'Long' },
			{ value: 'very_long', label: 'Very long' },
		],
		eye_color: [
			{ value: 'brown', label: 'Brown' },
			{ value: 'dark_brown', label: 'Dark brown' },
			{ value: 'blue', label: 'Blue' },
			{ value: 'green', label: 'Green' },
			{ value: 'hazel', label: 'Hazel' },
			{ value: 'gray', label: 'Gray' },
			{ value: 'amber', label: 'Amber' },
			{ value: 'black', label: 'Black' },
			{ value: 'red_violet', label: 'Red / violet (fantasy)' },
			{ value: 'heterochromia', label: 'Heterochromia' },
		],
		facial_hair: [
			{ value: 'none', label: 'None' },
			{ value: 'stubble', label: 'Stubble' },
			{ value: 'mustache', label: 'Mustache' },
			{ value: 'goatee', label: 'Goatee' },
			{ value: 'short_beard', label: 'Short beard' },
			{ value: 'full_beard', label: 'Full beard' },
		],
	},
};

export const FACE_REF_FIELD_LABELS: Record<string, string> = {
	image_style: 'Image style',
	sex: 'Sex / presentation',
	ethnicity: 'Ethnicity / appearance',
	age: 'Age',
	hair_color: 'Hair color',
	hair_length: 'Hair length',
	eye_color: 'Eye color',
	facial_hair: 'Facial hair',
};

/** Field order in the form (image style first). */
export const FACE_REF_FIELD_ORDER = [
	'image_style',
	'sex',
	'ethnicity',
	'age',
	'hair_color',
	'hair_length',
	'eye_color',
	'facial_hair',
] as const;
