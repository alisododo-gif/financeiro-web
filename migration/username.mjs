export const validUsername=(value,min=3)=>typeof value==='string'&&new RegExp('^[\\p{L}\\p{N}._-]{'+min+',80}$','u').test(value.trim());
